"""Fail-closed DUEL contract migration preflight."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine

from .config import Settings
from .database import create_database
from .ton import TonProviderError, normalize_address

ACTIVE_OFFER_STATES = ("pending_funding", "open", "reserved", "matched")
ACTIVE_DUEL_STATES = ("revealing",)
ACTIVE_INVITATION_STATES = ("accepted", "funding", "matched")


@dataclass(frozen=True)
class PreflightProof:
    previous_contract: str
    target_contract: str
    previous_locked_nano: int
    active_offers: int
    active_duels: int
    active_invitations: int


def _stack_number(item: Any) -> int:
    try:
        if not isinstance(item, list) or len(item) != 2 or item[0] != "num":
            raise ValueError
        return int(str(item[1]), 0)
    except (TypeError, ValueError) as exc:
        raise TonProviderError("malformed DUEL contractConfig numeric value") from exc


async def previous_contract_locked(
    http: httpx.AsyncClient,
    settings: Settings,
    address: str,
) -> int:
    response = await http.post(
        f"{settings.toncenter_url.rstrip('/')}/api/v2/runGetMethod",
        headers=(
            {"X-API-Key": settings.toncenter_api_key.get_secret_value()}
            if settings.toncenter_api_key.get_secret_value()
            else {}
        ),
        json={"address": address, "method": "contractConfig", "stack": []},
    )
    if response.status_code != 200:
        raise TonProviderError("TON provider rejected previous DUEL getter")
    payload: Any = response.json()
    if not isinstance(payload, dict):
        raise TonProviderError("previous DUEL contractConfig getter failed")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise TonProviderError("previous DUEL contractConfig getter failed")
    stack = result.get("stack")
    if (
        payload.get("ok") is not True
        or result.get("exit_code") != 0
        or not isinstance(stack, list)
        or len(stack) not in {5, 8}
    ):
        raise TonProviderError("previous DUEL contractConfig getter failed")
    locked = _stack_number(stack[-1])
    if locked < 0:
        raise TonProviderError("previous DUEL locked balance is negative")
    return locked


async def active_projection_counts(engine: AsyncEngine) -> tuple[int, int, int]:
    async with engine.connect() as connection:
        offers = await connection.scalar(
            text("SELECT COUNT(*) FROM duel_offers WHERE state IN :states")
            .bindparams(bindparam("states", expanding=True))
            .params(states=ACTIVE_OFFER_STATES)
        )
        duels = await connection.scalar(
            text("SELECT COUNT(*) FROM duels WHERE state IN :states")
            .bindparams(bindparam("states", expanding=True))
            .params(states=ACTIVE_DUEL_STATES)
        )
        invitations = await connection.scalar(
            text("SELECT COUNT(*) FROM duel_invitations WHERE state IN :states")
            .bindparams(bindparam("states", expanding=True))
            .params(states=ACTIVE_INVITATION_STATES)
        )
    return int(offers or 0), int(duels or 0), int(invitations or 0)


async def run_preflight(
    settings: Settings,
    previous_contract: str,
    target_contract: str,
    *,
    http: httpx.AsyncClient | None = None,
    engine: AsyncEngine | None = None,
) -> PreflightProof:
    previous = normalize_address(previous_contract)
    target = normalize_address(target_contract)
    configured = normalize_address(settings.effective_duel_contract_address)
    if previous == target:
        raise ValueError("previous and target DUEL contracts must differ")
    if configured != target:
        raise ValueError("configured DUEL contract does not match the target manifest")

    owns_http = http is None
    owns_engine = engine is None
    if http is None:
        http = httpx.AsyncClient(timeout=20)
    if engine is None:
        engine, _ = create_database(settings)
    try:
        locked = await previous_contract_locked(http, settings, previous)
        active_offers, active_duels, active_invitations = await active_projection_counts(engine)
    finally:
        if owns_http:
            await http.aclose()
        if owns_engine:
            await engine.dispose()

    proof = PreflightProof(
        previous_contract=previous,
        target_contract=target,
        previous_locked_nano=locked,
        active_offers=active_offers,
        active_duels=active_duels,
        active_invitations=active_invitations,
    )
    if locked != 0:
        raise RuntimeError(f"previous DUEL still locks {locked} nanotons")
    if active_offers or active_duels or active_invitations:
        raise RuntimeError(
            "DUEL projection is not idle: "
            f"offers={active_offers}, duels={active_duels}, invitations={active_invitations}"
        )
    return proof


async def _run(previous_contract: str, target_contract: str) -> int:
    try:
        proof = await run_preflight(Settings(), previous_contract, target_contract)
    except (httpx.HTTPError, TonProviderError, ValueError, RuntimeError) as exc:
        print(json.dumps({"ready": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"ready": True, **asdict(proof)}, ensure_ascii=False))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-contract", required=True)
    parser.add_argument("--target-contract", required=True)
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.previous_contract, args.target_contract)))


if __name__ == "__main__":
    main()
