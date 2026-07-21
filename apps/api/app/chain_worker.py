import asyncio
import base64
import enum
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from tonsdk.boc import Cell  # type: ignore[import-untyped]

from .config import get_settings
from .database import create_database
from .models import ChainCheckpoint, ReferralAttribution, ReferralReward, Wallet
from .modules.bank.models import BankChainEvent, BankPayout, BankPosition, BankPositionStatus
from .modules.duel.models import (
    ChallengeState,
    Duel,
    DuelChainEvent,
    DuelChallenge,
    DuelCommit,
    DuelPlayer,
    DuelReveal,
    DuelSettlement,
    DuelState,
    MatchmakingOffer,
    OfferState,
)
from .ton import TonClient, TonProviderError, normalize_address

logger = structlog.get_logger()

DUEL_OPEN_OFFER = 0x4C4F4F01
DUEL_CANCEL_OFFER = 0x4C4F4F02
DUEL_MATCH_OFFERS = 0x4C4F4F03
DUEL_REVEAL = 0x4C4F4F04
DUEL_EXPIRE_OFFER = 0x4C4F4F05
DUEL_EXPIRE_DUEL = 0x4C4F4F06
DUEL_PAYOUT = 0x4C4F4F11
DUEL_REFUND = 0x4C4F4F12
DUEL_PROTOCOL_FEE = 0x4C4F4F13

BANK_CREATE_POSITION = 0x4C424E01
BANK_PAYOUT = 0x4C424E11
BANK_PROTOCOL_FEE = 0x4C424E12

HEARTBEAT_FILE = Path("/tmp/loop-worker-heartbeat")  # noqa: S108


class ProjectionResult(enum.StrEnum):
    APPLIED = "applied"
    IGNORED = "ignored"
    RETRY = "retry"


def has_masterchain_finality(transaction: dict[str, Any]) -> bool:
    try:
        return int(transaction.get("mc_block_seqno") or 0) > 0
    except (TypeError, ValueError):
        return False


def successful_transaction(transaction: dict[str, Any]) -> bool:
    description = transaction.get("description") or {}
    compute = description.get("compute_ph") or {}
    action = description.get("action") or {}
    return bool(
        not transaction.get("emulated")
        and not description.get("aborted")
        and compute.get("success") is True
        and action.get("success") is not False
    )


def message_address(message: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = message.get(key)
        if isinstance(value, str) and value:
            try:
                return normalize_address(value)
            except TonProviderError:
                return None
    return None


def message_value(message: dict[str, Any]) -> int | None:
    value = message.get("value")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def decode_body(body_b64: str) -> dict[str, int]:
    cells = Cell.one_from_boc(base64.b64decode(body_b64))
    cell = cells[0] if isinstance(cells, list) else cells
    parser = cell.begin_parse()
    opcode = parser.read_uint(32)
    result = {"opcode": opcode, "query_id": parser.read_uint(64)}
    if opcode == DUEL_OPEN_OFFER:
        result.update(
            offer_id=parser.read_uint(64),
            commitment=parser.read_uint(256),
            chance_bps=parser.read_uint(16),
            total_pool_nano=parser.read_coins(),
            expires_at=parser.read_uint(32),
            counter_offer_id=parser.read_uint(64),
        )
    elif opcode in {DUEL_CANCEL_OFFER, DUEL_EXPIRE_OFFER}:
        result["offer_id"] = parser.read_uint(64)
    elif opcode == DUEL_MATCH_OFFERS:
        result.update(
            first_offer_id=parser.read_uint(64),
            second_offer_id=parser.read_uint(64),
        )
    elif opcode == DUEL_REVEAL:
        result.update(
            duel_id=parser.read_uint(64),
            offer_id=parser.read_uint(64),
            secret=parser.read_uint(256),
        )
    elif opcode == DUEL_EXPIRE_DUEL:
        result["duel_id"] = parser.read_uint(64)
    elif opcode == DUEL_PAYOUT:
        result.update(
            duel_id=parser.read_uint(64),
            offer_id=parser.read_uint(64),
            reason=parser.read_uint(8),
        )
    elif opcode == DUEL_REFUND:
        result.update(offer_id=parser.read_uint(64), reason=parser.read_uint(8))
    elif opcode == DUEL_PROTOCOL_FEE:
        result["duel_id"] = parser.read_uint(64)
    elif opcode == BANK_CREATE_POSITION:
        result.update(
            position_id=parser.read_uint(64),
            principal_nano=parser.read_coins(),
            multiplier_bps=parser.read_uint(16),
        )
    elif opcode == BANK_PAYOUT:
        result.update(
            position_id=parser.read_uint(64),
            principal_nano=parser.read_coins(),
            target_payout_nano=parser.read_coins(),
        )
    elif opcode == BANK_PROTOCOL_FEE:
        result["position_id"] = parser.read_uint(64)
    return result


def decode_outgoing(transaction: dict[str, Any]) -> list[dict[str, Any]]:
    decoded: list[dict[str, Any]] = []
    for index, message in enumerate(transaction.get("out_msgs") or []):
        if not isinstance(message, dict):
            continue
        body = (message.get("message_content") or {}).get("body")
        if not body:
            continue
        try:
            item: dict[str, Any] = decode_body(body)
        except Exception as exc:
            logger.debug("chain.outgoing_body_ignored", event_index=index + 1, error=str(exc))
            continue
        item.update(
            event_index=index + 1,
            destination=message_address(message, "destination", "dest", "destination_address"),
            value_nano=message_value(message),
        )
        decoded.append(item)
    return decoded


def transaction_identity(transaction: dict[str, Any]) -> tuple[int, str] | None:
    try:
        return int(transaction["lt"]), str(transaction["hash"])
    except (KeyError, TypeError, ValueError):
        return None


async def create_duel_projection(
    db: Any,
    settings: Any,
    transaction: dict[str, Any],
    first: MatchmakingOffer,
    second: MatchmakingOffer,
) -> None:
    first.state = OfferState.MATCHED.value
    second.state = OfferState.MATCHED.value
    first.reserved_until = None
    second.reserved_until = None
    ordered = sorted([first, second], key=lambda offer: offer.onchain_offer_id)
    duel_id = ordered[1].onchain_offer_id
    duel = await db.scalar(
        select(Duel).where(
            Duel.network == settings.ton_network_id,
            Duel.onchain_duel_id == duel_id,
        )
    )
    if duel is None:
        chain_time = datetime.fromtimestamp(
            int(transaction.get("now") or datetime.now(UTC).timestamp()), UTC
        )
        duel = Duel(
            onchain_duel_id=duel_id,
            network=settings.ton_network_id,
            offer_a_id=ordered[0].id,
            offer_b_id=ordered[1].id,
            reveal_deadline=chain_time.replace(microsecond=0)
            + timedelta(seconds=settings.reveal_ttl_seconds),
        )
        db.add(duel)
        await db.flush()
        for offer in ordered:
            db.add(
                DuelPlayer(
                    duel_id=duel.id,
                    offer_id=offer.id,
                    user_id=offer.user_id,
                    wallet_id=offer.wallet_id,
                    chance_bps=offer.chance_bps,
                    stake_nano=offer.stake_nano,
                )
            )
    challenge = await db.scalar(
        select(DuelChallenge).where(
            DuelChallenge.creator_offer_id.in_([first.id, second.id]),
            DuelChallenge.state.in_(
                [
                    ChallengeState.OPEN.value,
                    ChallengeState.ACCEPTED.value,
                    ChallengeState.FUNDING.value,
                ]
            ),
        )
    )
    if challenge:
        challenge.state = ChallengeState.MATCHED.value


async def apply_bank_transaction(
    db: Any,
    settings: Any,
    transaction: dict[str, Any],
    decoded: dict[str, int],
    outgoing: list[dict[str, Any]],
) -> ProjectionResult:
    identity = transaction_identity(transaction)
    if identity is None:
        return ProjectionResult.RETRY
    lt, tx_hash = identity
    existing = await db.scalar(
        select(BankChainEvent.id).where(
            BankChainEvent.network == settings.ton_network_id,
            BankChainEvent.account == settings.bank_contract_address,
            BankChainEvent.lt == lt,
            BankChainEvent.tx_hash == tx_hash,
            BankChainEvent.event_index == 0,
        )
    )
    if existing:
        return ProjectionResult.IGNORED
    opcode = decoded["opcode"]
    if opcode != BANK_CREATE_POSITION:
        return ProjectionResult.IGNORED
    position = await db.scalar(
        select(BankPosition).where(
            BankPosition.network == settings.ton_network_id,
            BankPosition.contract_address == settings.bank_contract_address,
            BankPosition.position_id == decoded["position_id"],
        )
    )
    if position is None:
        return ProjectionResult.IGNORED
    incoming = transaction.get("in_msg") or {}
    source = message_address(incoming, "source", "src", "source_address")
    value = message_value(incoming)
    expected_source = normalize_address(position.owner_wallet)
    if (
        source != expected_source
        or value is None
        or value < position.principal_nano + settings.bank_position_gas_nano
        or decoded["query_id"] != position.query_id
        or decoded["principal_nano"] != position.principal_nano
        or decoded["multiplier_bps"] != position.multiplier_bps
    ):
        return ProjectionResult.RETRY

    fee = position.principal_nano * settings.bank_fee_bps // 10_000
    available = position.principal_nano - fee
    older = (
        await db.scalars(
            select(BankPosition)
            .where(
                BankPosition.network == position.network,
                BankPosition.contract_address == position.contract_address,
                BankPosition.current_status.in_(
                    [
                        BankPositionStatus.QUEUED.value,
                        BankPositionStatus.PARTIALLY_FUNDED.value,
                    ]
                ),
            )
            .order_by(BankPosition.queue_index)
            .with_for_update()
        )
    ).all()
    payouts = {
        item["position_id"]: item
        for item in outgoing
        if item["opcode"] == BANK_PAYOUT and "position_id" in item
    }
    for earlier in older:
        if available <= 0:
            break
        allocation = min(available, earlier.remaining_amount_nano)
        earlier.funded_amount_nano += allocation
        earlier.remaining_amount_nano -= allocation
        available -= allocation
        if earlier.remaining_amount_nano == 0:
            payout = payouts.get(earlier.position_id)
            if (
                payout is None
                or payout.get("destination") != normalize_address(earlier.owner_wallet)
                or payout.get("value_nano") != earlier.target_payout_nano
            ):
                return ProjectionResult.RETRY
            earlier.current_status = BankPositionStatus.PAYOUT_SENT.value
            earlier.completed_at = datetime.fromtimestamp(int(transaction["now"]), UTC)
            earlier.payout_transaction = tx_hash
            if (
                await db.scalar(select(BankPayout.id).where(BankPayout.position_id == earlier.id))
                is None
            ):
                db.add(
                    BankPayout(
                        position_id=earlier.id,
                        network=earlier.network,
                        amount_nano=earlier.target_payout_nano,
                        destination=earlier.owner_wallet,
                        tx_hash=tx_hash,
                    )
                )
        else:
            earlier.current_status = BankPositionStatus.PARTIALLY_FUNDED.value

    next_queue = await db.scalar(
        select(func.max(BankPosition.queue_index)).where(
            BankPosition.network == position.network,
            BankPosition.contract_address == position.contract_address,
        )
    )
    position.queue_index = (next_queue if next_queue is not None else -1) + 1
    position.current_status = BankPositionStatus.QUEUED.value
    position.confirmed_at = datetime.fromtimestamp(int(transaction["now"]), UTC)
    position.funding_transaction = tx_hash
    event = BankChainEvent(
        network=position.network,
        account=position.contract_address,
        lt=lt,
        tx_hash=tx_hash,
        event_index=0,
        opcode=opcode,
        position_id=position.position_id,
        payload_json=json.dumps({"in": decoded, "out": outgoing}, separators=(",", ":")),
        applied=True,
    )
    db.add(event)
    return ProjectionResult.APPLIED


async def qualify_referral(db: Any, offer: MatchmakingOffer, duel: Duel, tx_hash: str) -> None:
    attribution = await db.scalar(
        select(ReferralAttribution).where(
            ReferralAttribution.invitee_user_id == offer.user_id,
            ReferralAttribution.status == "pending",
        )
    )
    if attribution is None:
        return
    inviter_wallet = await db.scalar(
        select(Wallet.address).where(
            Wallet.user_id == attribution.inviter_user_id,
            Wallet.active.is_(True),
        )
    )
    if inviter_wallet and normalize_address(inviter_wallet) == normalize_address(
        offer.owner_wallet
    ):
        attribution.status = "rejected"
        return
    attribution.status = "qualified"
    attribution.qualified_tx_hash = tx_hash
    attribution.qualified_at = datetime.now(UTC)
    existing = await db.scalar(
        select(ReferralReward.id).where(
            ReferralReward.attribution_id == attribution.id,
            ReferralReward.cause == f"duel:{duel.onchain_duel_id}",
        )
    )
    if existing is None:
        db.add(
            ReferralReward(
                attribution_id=attribution.id,
                cause=f"duel:{duel.onchain_duel_id}",
                reward_points=100,
            )
        )


async def apply_duel_transaction(
    db: Any,
    settings: Any,
    transaction: dict[str, Any],
    decoded: dict[str, int],
    outgoing: list[dict[str, Any]],
) -> ProjectionResult:
    identity = transaction_identity(transaction)
    if identity is None:
        return ProjectionResult.RETRY
    lt, tx_hash = identity
    account = settings.effective_duel_contract_address
    existing = await db.scalar(
        select(DuelChainEvent.id).where(
            DuelChainEvent.network == settings.ton_network_id,
            DuelChainEvent.account == account,
            DuelChainEvent.lt == lt,
            DuelChainEvent.tx_hash == tx_hash,
            DuelChainEvent.event_index == 0,
        )
    )
    if existing:
        return ProjectionResult.IGNORED
    opcode = decoded["opcode"]
    incoming = transaction.get("in_msg") or {}
    source = message_address(incoming, "source", "src", "source_address")
    value = message_value(incoming)

    if opcode == DUEL_OPEN_OFFER:
        offer = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.onchain_offer_id == decoded["offer_id"],
            )
        )
        if offer is None:
            return ProjectionResult.IGNORED
        if (
            source != normalize_address(offer.owner_wallet)
            or value is None
            or value < offer.stake_nano + settings.offer_gas_nano
            or decoded["query_id"] != offer.query_id
            or decoded["commitment"] != int(offer.commitment_hex, 16)
            or decoded["chance_bps"] != offer.chance_bps
            or decoded["total_pool_nano"] != offer.total_pool_nano
            or decoded["counter_offer_id"] != offer.counter_offer_id
            or decoded["expires_at"] != int(offer.expires_at.timestamp())
        ):
            return ProjectionResult.RETRY
        offer.state = OfferState.OPEN.value
        offer.funding_tx_hash = tx_hash
        offer.reserved_until = None
        if await db.scalar(select(DuelCommit.id).where(DuelCommit.offer_id == offer.id)) is None:
            db.add(
                DuelCommit(
                    offer_id=offer.id,
                    commitment_hex=offer.commitment_hex,
                    tx_hash=tx_hash,
                )
            )
        if offer.counter_offer_id:
            counter = await db.scalar(
                select(MatchmakingOffer).where(
                    MatchmakingOffer.network == settings.ton_network_id,
                    MatchmakingOffer.onchain_offer_id == offer.counter_offer_id,
                )
            )
            if counter is None or counter.state not in {
                OfferState.OPEN.value,
                OfferState.RESERVED.value,
            }:
                return ProjectionResult.RETRY
            await create_duel_projection(db, settings, transaction, counter, offer)
    elif opcode == DUEL_MATCH_OFFERS:
        first = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.onchain_offer_id == decoded["first_offer_id"],
            )
        )
        second = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.onchain_offer_id == decoded["second_offer_id"],
            )
        )
        if first is None or second is None:
            return ProjectionResult.RETRY
        await create_duel_projection(db, settings, transaction, first, second)
    elif opcode in {DUEL_CANCEL_OFFER, DUEL_EXPIRE_OFFER}:
        offer = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.onchain_offer_id == decoded["offer_id"],
            )
        )
        if offer is None:
            return ProjectionResult.IGNORED
        if opcode == DUEL_CANCEL_OFFER and source != normalize_address(offer.owner_wallet):
            return ProjectionResult.RETRY
        offer.state = (
            OfferState.CANCELLED.value if opcode == DUEL_CANCEL_OFFER else OfferState.EXPIRED.value
        )
    elif opcode == DUEL_REVEAL:
        offer = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.onchain_offer_id == decoded["offer_id"],
            )
        )
        if offer is None or source != normalize_address(offer.owner_wallet):
            return ProjectionResult.RETRY
        offer.revealed = True
        duel = await db.scalar(
            select(Duel).where(
                Duel.network == settings.ton_network_id,
                Duel.onchain_duel_id == decoded["duel_id"],
            )
        )
        if (
            duel
            and await db.scalar(select(DuelReveal.id).where(DuelReveal.offer_id == offer.id))
            is None
        ):
            db.add(DuelReveal(duel_id=duel.id, offer_id=offer.id, tx_hash=tx_hash))

    payouts = [item for item in outgoing if item["opcode"] == DUEL_PAYOUT]
    refunds = [item for item in outgoing if item["opcode"] == DUEL_REFUND]
    for refund in refunds:
        offer = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.onchain_offer_id == refund["offer_id"],
            )
        )
        if offer is None:
            return ProjectionResult.RETRY
        if (
            refund.get("destination") != normalize_address(offer.owner_wallet)
            or refund.get("value_nano") != offer.stake_nano
        ):
            return ProjectionResult.RETRY
        offer.state = OfferState.REFUNDED.value
    for payout in payouts:
        duel = await db.scalar(
            select(Duel).where(
                Duel.network == settings.ton_network_id,
                Duel.onchain_duel_id == payout["duel_id"],
            )
        )
        winner = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.onchain_offer_id == payout["offer_id"],
            )
        )
        if duel is None or winner is None:
            return ProjectionResult.RETRY
        if (
            payout.get("destination") != normalize_address(winner.owner_wallet)
            or payout.get("value_nano") != winner.payout_nano
        ):
            return ProjectionResult.RETRY
        first = await db.get(MatchmakingOffer, duel.offer_a_id)
        second = await db.get(MatchmakingOffer, duel.offer_b_id)
        if first is None or second is None:
            return ProjectionResult.RETRY
        duel.state = DuelState.SETTLED.value
        duel.winner_wallet = winner.owner_wallet
        duel.settled_tx_hash = tx_hash
        duel.settled_at = datetime.fromtimestamp(int(transaction["now"]), UTC)
        first.state = OfferState.SETTLED.value
        second.state = OfferState.SETTLED.value
        if (
            await db.scalar(select(DuelSettlement.id).where(DuelSettlement.duel_id == duel.id))
            is None
        ):
            db.add(
                DuelSettlement(
                    duel_id=duel.id,
                    winner_wallet=winner.owner_wallet,
                    payout_nano=winner.payout_nano,
                    fee_nano=winner.total_pool_nano - winner.payout_nano,
                    outcome="settled",
                    tx_hash=tx_hash,
                )
            )
        await qualify_referral(db, first, duel, tx_hash)
        await qualify_referral(db, second, duel, tx_hash)

    event = DuelChainEvent(
        network=settings.ton_network_id,
        account=account,
        lt=lt,
        tx_hash=tx_hash,
        event_index=0,
        opcode=opcode,
        payload_json=json.dumps({"in": decoded, "out": outgoing}, separators=(",", ":")),
        applied=True,
    )
    try:
        async with db.begin_nested():
            db.add(event)
            await db.flush()
    except IntegrityError:
        return ProjectionResult.IGNORED
    return ProjectionResult.APPLIED


async def apply_transaction(
    db: Any,
    settings: Any,
    transaction: dict[str, Any],
    mode: str | None = None,
) -> ProjectionResult:
    if not has_masterchain_finality(transaction):
        return ProjectionResult.RETRY
    if not successful_transaction(transaction):
        return ProjectionResult.IGNORED
    account = message_address(transaction, "account")
    bank_account = (
        normalize_address(settings.bank_contract_address)
        if settings.bank_contract_address
        else None
    )
    duel_account = (
        normalize_address(settings.effective_duel_contract_address)
        if settings.effective_duel_contract_address
        else None
    )
    actual_mode = mode or (
        "bank" if account == bank_account else "duel" if account == duel_account else None
    )
    if actual_mode is None:
        return ProjectionResult.IGNORED
    expected = bank_account if actual_mode == "bank" else duel_account
    if account != expected:
        return ProjectionResult.IGNORED
    incoming = transaction.get("in_msg") or {}
    body = (incoming.get("message_content") or {}).get("body")
    if not body:
        return ProjectionResult.RETRY
    try:
        decoded = decode_body(body)
    except Exception:
        return ProjectionResult.RETRY
    outgoing = decode_outgoing(transaction)
    if actual_mode == "bank":
        return await apply_bank_transaction(db, settings, transaction, decoded, outgoing)
    return await apply_duel_transaction(db, settings, transaction, decoded, outgoing)


async def run_contract_once(
    http: httpx.AsyncClient,
    session_factory: Any,
    settings: Any,
    *,
    mode: str,
    address: str,
) -> int:
    if not address:
        return 0
    key = f"{mode}:{settings.ton_network_id}:{address}"
    async with session_factory() as db:
        checkpoint = await db.get(ChainCheckpoint, key)
        start_lt = max((checkpoint.last_lt if checkpoint else 0) - 1, 0)
    response = await http.get(
        f"{settings.toncenter_url}/api/v3/transactions",
        params={"account": address, "start_lt": start_lt, "limit": 100, "sort": "asc"},
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
            if not has_masterchain_finality(transaction):
                break
            savepoint = await db.begin_nested()
            try:
                result = await apply_transaction(db, settings, transaction, mode)
            except Exception:
                await savepoint.rollback()
                raise
            if result == ProjectionResult.RETRY:
                await savepoint.rollback()
                break
            await savepoint.commit()
            if result == ProjectionResult.APPLIED:
                applied += 1
            checkpoint.last_lt = max(checkpoint.last_lt, int(transaction["lt"]) + 1)
        checkpoint.heartbeat_at = datetime.now(UTC)
        await db.execute(
            update(MatchmakingOffer)
            .where(
                MatchmakingOffer.state == OfferState.RESERVED.value,
                MatchmakingOffer.reserved_until < datetime.now(UTC),
                MatchmakingOffer.mode == "afk",
            )
            .values(state=OfferState.OPEN.value, reserved_until=None)
        )
        await db.execute(
            update(DuelChallenge)
            .where(
                DuelChallenge.state.in_(
                    [
                        ChallengeState.OPEN.value,
                        ChallengeState.ACCEPTED.value,
                        ChallengeState.FUNDING.value,
                    ]
                ),
                DuelChallenge.expires_at < datetime.now(UTC),
            )
            .values(state=ChallengeState.EXPIRED.value)
        )
        await db.commit()
    return applied


async def run_once(http: httpx.AsyncClient, session_factory: Any, settings: Any) -> int:
    bank = await run_contract_once(
        http,
        session_factory,
        settings,
        mode="bank",
        address=settings.bank_contract_address,
    )
    duel = await run_contract_once(
        http,
        session_factory,
        settings,
        mode="duel",
        address=settings.effective_duel_contract_address,
    )
    await asyncio.to_thread(
        HEARTBEAT_FILE.write_text,
        str(int(datetime.now(UTC).timestamp())),
        encoding="utf-8",
    )
    return bank + duel


async def attest_contracts(http: httpx.AsyncClient, settings: Any) -> None:
    client = TonClient(http, settings)
    pairs = [
        (settings.bank_contract_address, settings.bank_contract_code_hash, "BANK"),
        (
            settings.effective_duel_contract_address,
            settings.effective_duel_contract_code_hash,
            "DUEL",
        ),
    ]
    for address, expected, mode in pairs:
        if not address or not expected:
            raise RuntimeError(f"{mode} contract attestation is not configured")
        actual = await client.get_contract_code_hash(address)
        if actual != expected.removeprefix("0x").upper():
            raise RuntimeError(f"{mode} contract code hash mismatch")


async def main() -> None:
    settings = get_settings()
    engine, session_factory = create_database(settings)
    timeout = httpx.Timeout(15.0, connect=3.0)
    async with httpx.AsyncClient(timeout=timeout) as http:
        await attest_contracts(http, settings)
        while True:
            try:
                await run_once(http, session_factory, settings)
            except Exception as exc:
                logger.error("chain_worker_failed", error=type(exc).__name__)
            await asyncio.sleep(5)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
