import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from tonsdk.boc import Cell

from .config import get_settings
from .database import create_database
from .models import ChainCheckpoint, ChainEvent, Duel, DuelState, MatchmakingOffer, OfferState

logger = structlog.get_logger()
OPEN_OFFER = 0x4C4F4F01
CANCEL_OFFER = 0x4C4F4F02
REVEAL = 0x4C4F4F04
EXPIRE_OFFER = 0x4C4F4F05
EXPIRE_DUEL = 0x4C4F4F06


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
    elif opcode == REVEAL:
        result.update(
            duel_id=parser.read_uint(64),
            offer_id=parser.read_uint(64),
            secret=parser.read_uint(256),
        )
    elif opcode == EXPIRE_DUEL:
        result["duel_id"] = parser.read_uint(64)
    return result


async def apply_transaction(db: Any, settings: Any, transaction: dict[str, Any]) -> None:
    description = transaction.get("description", {})
    compute = description.get("compute_ph") or {}
    action = description.get("action") or {}
    if description.get("aborted") or not compute.get("success") or action.get("success") is False:
        return
    incoming = transaction.get("in_msg") or {}
    content = incoming.get("message_content") or {}
    body = content.get("body")
    if not body:
        return
    decoded = decode_body(body)
    event = ChainEvent(
        network=settings.ton_network_id,
        account=settings.ton_contract_address,
        lt=int(transaction["lt"]),
        tx_hash=transaction["hash"],
        opcode=decoded["opcode"],
        body_hash=content.get("hash"),
        payload_json=json.dumps(decoded, separators=(",", ":")),
    )
    db.add(event)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return
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
                counter = await db.scalar(
                    select(MatchmakingOffer).where(
                        MatchmakingOffer.onchain_offer_id == decoded["counter_offer_id"]
                    )
                )
                if counter:
                    counter.state = OfferState.MATCHED.value
                    db.add(
                        Duel(
                            onchain_duel_id=offer.onchain_offer_id,
                            network=settings.ton_network_id,
                            offer_a_id=counter.id,
                            offer_b_id=offer.id,
                            reveal_deadline=datetime.now(UTC)
                            + timedelta(seconds=settings.reveal_ttl_seconds),
                        )
                    )
    elif opcode in {CANCEL_OFFER, EXPIRE_OFFER}:
        offer = await db.scalar(
            select(MatchmakingOffer).where(MatchmakingOffer.onchain_offer_id == decoded["offer_id"])
        )
        if offer:
            offer.state = (
                OfferState.CANCELLED.value if opcode == CANCEL_OFFER else OfferState.EXPIRED.value
            )
    elif opcode == REVEAL:
        offer = await db.scalar(
            select(MatchmakingOffer).where(MatchmakingOffer.onchain_offer_id == decoded["offer_id"])
        )
        if offer:
            offer.revealed = True
    elif opcode == EXPIRE_DUEL:
        duel = await db.scalar(select(Duel).where(Duel.onchain_duel_id == decoded["duel_id"]))
        if duel:
            duel.state = DuelState.EXPIRED.value
            duel.settled_tx_hash = transaction["hash"]
            duel.settled_at = datetime.now(UTC)
    event.applied = True


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
            await apply_transaction(db, settings, transaction)
            checkpoint.last_lt = max(checkpoint.last_lt, int(transaction["lt"]) + 1)
            applied += 1
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
