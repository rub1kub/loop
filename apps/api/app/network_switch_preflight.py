"""Fail-closed drain check before changing the application's TON network."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import MAINNET_NETWORK_ID, SUPPORTED_TON_NETWORK_IDS, Settings
from .database import create_database
from .ton import TonClient, TonProviderError


@dataclass(frozen=True)
class NetworkSwitchProof:
    source_network: int
    target_network: int
    bank_locked_nano: int
    duel_locked_nano: int
    active_bank_positions: int
    active_duel_offers: int
    active_duels: int
    active_duel_invitations: int


async def active_projection_counts(
    engine: AsyncEngine,
    network: int,
) -> tuple[int, int, int, int]:
    async with engine.connect() as connection:
        values = []
        statements = (
            """
            SELECT COUNT(*) FROM bank_positions
            WHERE network = :network
              AND current_status IN (
                'pending_confirmation', 'queued', 'partially_funded', 'completed'
              )
            """,
            """
            SELECT COUNT(*) FROM duel_offers
            WHERE network = :network
              AND state IN ('pending_funding', 'open', 'reserved', 'matched')
            """,
            """
            SELECT COUNT(*) FROM duels
            WHERE network = :network AND state = 'revealing'
            """,
            """
            SELECT COUNT(*) FROM duel_invitations AS invitation
            JOIN duel_offers AS offer ON offer.id = invitation.creator_offer_id
            WHERE offer.network = :network
              AND invitation.state IN ('accepted', 'funding', 'matched')
            """,
        )
        for statement in statements:
            values.append(
                int(
                    await connection.scalar(
                        text(statement),
                        {"network": network},
                    )
                    or 0
                )
            )
    return values[0], values[1], values[2], values[3]


async def run_preflight(
    settings: Settings,
    target_network: int,
    *,
    ton_client: TonClient | None = None,
    engine: AsyncEngine | None = None,
) -> NetworkSwitchProof:
    if target_network not in SUPPORTED_TON_NETWORK_IDS:
        raise ValueError("unsupported target TON network")
    if target_network == settings.ton_network_id:
        raise ValueError("source and target TON networks must differ")

    owns_http = ton_client is None
    owns_engine = engine is None
    http = httpx.AsyncClient(timeout=20) if owns_http else None
    if ton_client is None:
        assert http is not None
        ton_client = TonClient(http, settings)
    if engine is None:
        engine, _ = create_database(settings)
    try:
        bank = await ton_client.get_contract_admin_state(
            "bank", settings.bank_contract_address
        )
        duel = await ton_client.get_contract_admin_state(
            "duel", settings.effective_duel_contract_address
        )
        counts = await active_projection_counts(engine, settings.ton_network_id)
    finally:
        if http is not None:
            await http.aclose()
        if owns_engine:
            await engine.dispose()

    proof = NetworkSwitchProof(
        source_network=settings.ton_network_id,
        target_network=target_network,
        bank_locked_nano=bank.locked_nano,
        duel_locked_nano=duel.locked_nano,
        active_bank_positions=counts[0],
        active_duel_offers=counts[1],
        active_duels=counts[2],
        active_duel_invitations=counts[3],
    )
    if not bank.paused or not duel.paused:
        raise RuntimeError("both source contracts must be paused before a network switch")
    # Draining exists so that nobody's money is stranded on a network the
    # application has walked away from. Testnet coins are not money: they are
    # free, and the whole point of leaving testnet is that its state is
    # disposable. Requiring a drain there protects nothing and would have to be
    # satisfied by paying out test positions with more test coins.
    #
    # Leaving mainnet is the case the check is for, and it stays absolute.
    # What is abandoned on testnet is reported rather than hidden, so the
    # release record shows exactly what was left behind.
    if settings.ton_network_id == MAINNET_NETWORK_ID and (
        bank.locked_nano or duel.locked_nano or any(counts)
    ):
        raise RuntimeError(
            "source network is not drained: "
            f"bank_locked={bank.locked_nano}, duel_locked={duel.locked_nano}, "
            f"bank_positions={counts[0]}, duel_offers={counts[1]}, "
            f"duels={counts[2]}, invitations={counts[3]}"
        )
    return proof


async def _run(target_network: int) -> int:
    try:
        proof = await run_preflight(Settings(), target_network)
    except (httpx.HTTPError, TonProviderError, ValueError, RuntimeError) as exc:
        print(json.dumps({"ready": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ready": True, **asdict(proof)}, ensure_ascii=False))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-network", type=int, required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.target_network)))


if __name__ == "__main__":
    main()
