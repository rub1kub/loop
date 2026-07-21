import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from tonsdk.boc import Cell  # type: ignore[import-untyped]

from .config import get_settings
from .database import create_database
from .models import (
    ChainCheckpoint,
    ChainEvent,
    Duel,
    DuelState,
    MatchmakingOffer,
    OfferState,
    Wallet,
)

logger = structlog.get_logger()
OPEN_OFFER = 0x4C4F4F01
CANCEL_OFFER = 0x4C4F4F02
MATCH_OFFERS = 0x4C4F4F03
REVEAL = 0x4C4F4F04
EXPIRE_OFFER = 0x4C4F4F05
EXPIRE_DUEL = 0x4C4F4F06
DUEL_PAYOUT = 0x4C4F4F11
OFFER_REFUND = 0x4C4F4F12
PROTOCOL_FEE = 0x4C4F4F13


def decode_body(body_b64: str) -> dict[str, int]:
    cells = Cell.one_from_boc(base64.b64decode(body_b64))
    cell = cells[0] if isinstance(cells, list) else cells
    parser = cell.begin_parse()
    opcode = parser.read_uint(32)
    result = {"opcode": opcode, "query_id": parser.read_uint(64)}
    if opcode == OPEN_OFFER:
        result.update(
            offer_id=parser.read_uint(64),
            commitment=parser.read_uint(256),
            chance_bps=parser.read_uint(16),
            total_pool_nano=parser.read_coins(),
            expires_at=parser.read_uint(32),
            counter_offer_id=parser.read_uint(64),
        )
    elif opcode in {CANCEL_OFFER, EXPIRE_OFFER}:
        result["offer_id"] = parser.read_uint(64)
    elif opcode == MATCH_OFFERS:
        result.update(
            first_offer_id=parser.read_uint(64), second_offer_id=parser.read_uint(64)
        )
    elif opcode == REVEAL:
        result.update(
            duel_id=parser.read_uint(64),
            offer_id=parser.read_uint(64),
            secret=parser.read_uint(256),
        )
    elif opcode == EXPIRE_DUEL:
        result["duel_id"] = parser.read_uint(64)
    elif opcode == DUEL_PAYOUT:
        result.update(
            duel_id=parser.read_uint(64),
            offer_id=parser.read_uint(64),
            reason=parser.read_uint(8),
        )
    elif opcode == OFFER_REFUND:
        result.update(offer_id=parser.read_uint(64), reason=parser.read_uint(8))
    elif opcode == PROTOCOL_FEE:
        result["duel_id"] = parser.read_uint(64)
    return result


def decode_outgoing(transaction: dict[str, Any]) -> list[dict[str, int]]:
    decoded: list[dict[str, int]] = []
    for message in transaction.get("out_msgs") or []:
        if not isinstance(message, dict):
            continue
        body = (message.get("message_content") or {}).get("body")
        if not body:
            continue
        try:
            item = decode_body(body)
        except Exception as exc:
            logger.debug("outgoing_body_ignored", error=type(exc).__name__)
            continue
        if item["opcode"] in {DUEL_PAYOUT, OFFER_REFUND, PROTOCOL_FEE}:
            decoded.append(item)
    return decoded


async def load_duel_offers(
    db: Any, duel: Duel
) -> tuple[MatchmakingOffer | None, MatchmakingOffer | None]:
    return (
        await db.get(MatchmakingOffer, duel.offer_a_id),
        await db.get(MatchmakingOffer, duel.offer_b_id),
    )


async def match_projection(
    db: Any,
    settings: Any,
    transaction: dict[str, Any],
    first_offer_id: int,
    second_offer_id: int,
) -> None:
    first = await db.scalar(
        select(MatchmakingOffer).where(
            MatchmakingOffer.onchain_offer_id == first_offer_id,
            MatchmakingOffer.network == settings.ton_network_id,
        )
    )
    second = await db.scalar(
        select(MatchmakingOffer).where(
            MatchmakingOffer.onchain_offer_id == second_offer_id,
            MatchmakingOffer.network == settings.ton_network_id,
        )
    )
    if first is None or second is None:
        return
    first.state = OfferState.MATCHED.value
    second.state = OfferState.MATCHED.value
    offer_a, offer_b = sorted([first, second], key=lambda item: item.onchain_offer_id)
    duel_id = offer_b.onchain_offer_id
    existing_duel = await db.scalar(
        select(Duel.id).where(
            Duel.onchain_duel_id == duel_id,
            Duel.network == settings.ton_network_id,
        )
    )
    if existing_duel is not None:
        return
    chain_time = datetime.fromtimestamp(
        int(transaction.get("now") or datetime.now(UTC).timestamp()), UTC
    )
    db.add(
        Duel(
            onchain_duel_id=duel_id,
            network=settings.ton_network_id,
            offer_a_id=offer_a.id,
            offer_b_id=offer_b.id,
            reveal_deadline=chain_time + timedelta(seconds=settings.reveal_ttl_seconds),
        )
    )


async def settle_projection(
    db: Any,
    settings: Any,
    transaction: dict[str, Any],
    duel_id: int,
    winner_offer_id: int | None,
) -> None:
    duel = await db.scalar(
        select(Duel).where(
            Duel.onchain_duel_id == duel_id,
            Duel.network == settings.ton_network_id,
        )
    )
    if duel is None:
        return
    first, second = await load_duel_offers(db, duel)
    if first is None or second is None:
        return
    timestamp = datetime.fromtimestamp(
        int(transaction.get("now") or datetime.now(UTC).timestamp()), UTC
    )
    if winner_offer_id is None:
        duel.state = DuelState.REFUNDED.value
        first.state = OfferState.REFUNDED.value
        second.state = OfferState.REFUNDED.value
    else:
        winner_offer = first if first.onchain_offer_id == winner_offer_id else second
        if winner_offer.onchain_offer_id != winner_offer_id:
            return
        wallet = await db.get(Wallet, winner_offer.wallet_id)
        duel.state = DuelState.SETTLED.value
        duel.winner_wallet = wallet.address if wallet else None
        first.state = OfferState.SETTLED.value
        second.state = OfferState.SETTLED.value
    duel.settled_tx_hash = transaction["hash"]
    duel.settled_at = timestamp


async def apply_transaction(db: Any, settings: Any, transaction: dict[str, Any]) -> bool:
    description = transaction.get("description", {})
    compute = description.get("compute_ph") or {}
    action = description.get("action") or {}
    if (
        transaction.get("emulated")
        or description.get("aborted")
        or not compute.get("success")
        or action.get("success") is False
    ):
        return False
    incoming = transaction.get("in_msg") or {}
    content = incoming.get("message_content") or {}
    body = content.get("body")
    if not body:
        return False
    try:
        decoded = decode_body(body)
    except Exception:
        return False
    identity = (
        await db.scalar(
            select(ChainEvent.id).where(
                ChainEvent.network == settings.ton_network_id,
                ChainEvent.account == settings.ton_contract_address,
                ChainEvent.lt == int(transaction["lt"]),
                ChainEvent.tx_hash == transaction["hash"],
            )
        )
    )
    if identity:
        return False
    outgoing = decode_outgoing(transaction)
    event = ChainEvent(
        network=settings.ton_network_id,
        account=settings.ton_contract_address,
        lt=int(transaction["lt"]),
        tx_hash=transaction["hash"],
        opcode=decoded["opcode"],
        body_hash=content.get("hash"),
        payload_json=json.dumps({"in": decoded, "out": outgoing}, separators=(",", ":")),
    )
    try:
        async with db.begin_nested():
            db.add(event)
            await db.flush()
    except IntegrityError:
        return False
    opcode = decoded["opcode"]
    if opcode == OPEN_OFFER:
        offer = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.onchain_offer_id == decoded["offer_id"],
                MatchmakingOffer.network == settings.ton_network_id,
            )
        )
        if offer:
            offer.state = (
                OfferState.MATCHED.value if decoded["counter_offer_id"] else OfferState.OPEN.value
            )
            offer.funding_tx_hash = transaction["hash"]
            if decoded["counter_offer_id"]:
                await match_projection(
                    db,
                    settings,
                    transaction,
                    decoded["counter_offer_id"],
                    decoded["offer_id"],
                )
    elif opcode == MATCH_OFFERS:
        await match_projection(
            db,
            settings,
            transaction,
            decoded["first_offer_id"],
            decoded["second_offer_id"],
        )
    elif opcode in {CANCEL_OFFER, EXPIRE_OFFER}:
        offer = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.onchain_offer_id == decoded["offer_id"],
                MatchmakingOffer.network == settings.ton_network_id,
            )
        )
        if offer:
            offer.state = (
                OfferState.CANCELLED.value if opcode == CANCEL_OFFER else OfferState.EXPIRED.value
            )
    elif opcode == REVEAL:
        offer = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.onchain_offer_id == decoded["offer_id"],
                MatchmakingOffer.network == settings.ton_network_id,
            )
        )
        if offer:
            offer.revealed = True
    payout = next((item for item in outgoing if item["opcode"] == DUEL_PAYOUT), None)
    if payout:
        await settle_projection(
            db,
            settings,
            transaction,
            payout["duel_id"],
            payout["offer_id"],
        )
    elif opcode == EXPIRE_DUEL:
        duel = await db.scalar(
            select(Duel).where(
                Duel.onchain_duel_id == decoded["duel_id"],
                Duel.network == settings.ton_network_id,
            )
        )
        if duel:
            first, second = await load_duel_offers(db, duel)
            winner_id = None
            if first and second and first.revealed != second.revealed:
                winner_id = first.onchain_offer_id if first.revealed else second.onchain_offer_id
            await settle_projection(
                db, settings, transaction, decoded["duel_id"], winner_id
            )
    event.applied = True
    return True


async def run_once(http: httpx.AsyncClient, session_factory: Any, settings: Any) -> int:
    if not settings.ton_contract_address:
        return 0
    key = f"{settings.ton_network_id}:{settings.ton_contract_address}"
    async with session_factory() as db:
        checkpoint = await db.get(ChainCheckpoint, key)
        start_lt = max((checkpoint.last_lt if checkpoint else 0) - 1, 0)
    response = await http.get(
        f"{settings.toncenter_url}/api/v3/transactions",
        params={
            "account": settings.ton_contract_address,
            "start_lt": start_lt,
            "limit": 100,
            "sort": "asc",
        },
        headers=(
            {"X-API-Key": settings.toncenter_api_key.get_secret_value()}
            if settings.toncenter_api_key.get_secret_value()
            else {}
        ),
    )
    response.raise_for_status()
    transactions = response.json().get("transactions", [])
    applied = 0
    async with session_factory() as db:
        checkpoint = await db.get(ChainCheckpoint, key) or ChainCheckpoint(key=key, last_lt=0)
        db.add(checkpoint)
        for transaction in transactions:
            if await apply_transaction(db, settings, transaction):
                applied += 1
            checkpoint.last_lt = max(checkpoint.last_lt, int(transaction["lt"]) + 1)
        await db.execute(
            update(MatchmakingOffer)
            .where(
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.state == OfferState.PENDING_FUNDING.value,
                MatchmakingOffer.expires_at < datetime.now(UTC),
            )
            .values(state=OfferState.REJECTED.value)
        )
        await db.commit()
    return applied


async def main() -> None:
    settings = get_settings()
    engine, session_factory = create_database(settings)
    timeout = httpx.Timeout(15.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout) as http:
        while True:
            try:
                await run_once(http, session_factory, settings)
            except Exception as exc:
                logger.error("chain_worker_failed", error=type(exc).__name__)
            await asyncio.sleep(5)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
