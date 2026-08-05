import asyncio
import base64
import enum
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from tonsdk.boc import Cell  # type: ignore[import-untyped]

from .config import get_settings
from .control_state import contract_control_key
from .database import create_database
from .duel_notifications import (
    KIND_DUEL_MATCHED,
    KIND_DUEL_REVEAL_SOON,
    KIND_REFERRAL_QUALIFIED,
)
from .models import (
    AdminAuditEvent,
    ChainCheckpoint,
    ContractControl,
    NotificationOutbox,
    ReferralAttribution,
    ReferralReward,
    Wallet,
)
from .modules.bank.models import BankChainEvent, BankPayout, BankPosition, BankPositionStatus
from .modules.duel.models import (
    ChallengeState,
    Duel,
    DuelBoost,
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
from .public_feed import enqueue_public_feed
from .result_cards import create_entry_card, create_result_card
from .ton import (
    TonClient,
    TonProviderError,
    normalize_address,
    verify_direct_accept_permit,
    verify_holder_fee_permit,
)

logger = structlog.get_logger()

DUEL_OPEN_OFFER = 0x4C4F4F01
DUEL_CANCEL_OFFER = 0x4C4F4F02
DUEL_MATCH_OFFERS = 0x4C4F4F03
DUEL_REVEAL = 0x4C4F4F04
DUEL_EXPIRE_OFFER = 0x4C4F4F05
DUEL_EXPIRE_DUEL = 0x4C4F4F06
DUEL_OPEN_DIRECT_OFFER = 0x4C4F4F08
DUEL_ACCEPT_DIRECT_OFFER = 0x4C4F4F09
DUEL_FUND_RESERVE = 0x4C4F4F0A
DUEL_WITHDRAW_SURPLUS = 0x4C4F4F0B
DUEL_SET_FEE = 0x4C4F4F0C
DUEL_SET_TREASURY = 0x4C4F4F0D
DUEL_SET_OWNER = 0x4C4F4F0E
DUEL_BOOST = 0x4C4F4F0F
DUEL_PAYOUT = 0x4C4F4F11
DUEL_REFUND = 0x4C4F4F12
DUEL_PROTOCOL_FEE = 0x4C4F4F13
DUEL_ADMIN_WITHDRAWAL = 0x4C4F4F14

BANK_CREATE_POSITION = 0x4C424E01
BANK_SET_PAUSED = 0x4C424E02
BANK_FUND_RESERVE = 0x4C424E03
BANK_WITHDRAW_SURPLUS = 0x4C424E04
BANK_SET_FEE = 0x4C424E05
BANK_SET_TREASURY = 0x4C424E06
BANK_SET_OWNER = 0x4C424E07
BANK_PAYOUT = 0x4C424E11
BANK_PROTOCOL_FEE = 0x4C424E12
BANK_ADMIN_WITHDRAWAL = 0x4C424E13

DUEL_SET_PAUSED = 0x4C4F4F07

# Mirrors MAX_EXPIRY_DELAY in contracts/duel/DuelEscrow.tolk.
DUEL_MAX_EXPIRY_DELAY = 3_600

BANK_ADMIN_OPCODES = {
    BANK_SET_PAUSED,
    BANK_FUND_RESERVE,
    BANK_WITHDRAW_SURPLUS,
    BANK_SET_FEE,
    BANK_SET_TREASURY,
    BANK_SET_OWNER,
}
DUEL_ADMIN_OPCODES = {
    DUEL_SET_PAUSED,
    DUEL_FUND_RESERVE,
    DUEL_WITHDRAW_SURPLUS,
    DUEL_SET_FEE,
    DUEL_SET_TREASURY,
    DUEL_SET_OWNER,
}

HEARTBEAT_FILE = Path("/tmp/loop-worker-heartbeat")  # noqa: S108


class ProjectionResult(enum.StrEnum):
    APPLIED = "applied"
    IGNORED = "ignored"
    RETRY = "retry"


ALERT_AFTER_FAILURES = 3


async def announce(http: httpx.AsyncClient, settings: Any, text: str) -> None:
    """Tell a human the projection stopped. Never the reason the worker dies."""
    chat_id = getattr(settings, "alert_chat_id", 0)
    token = settings.bot_token.get_secret_value()
    if not chat_id or not token:
        return
    try:
        await http.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
    except Exception as exc:  # noqa: BLE001 — an unsent alert must not stop the retry loop
        logger.warning("chain_worker_alert_failed", error=type(exc).__name__, detail=str(exc))


class ProjectionFailure(Exception):
    """One transaction the projection could not write down, and which one.

    Raised after the cycle has committed everything that did apply, so the
    checkpoint stands where the trouble starts. It carries the contract and the
    transaction hash because a bare exception type is not enough to find the
    row: on 2026-08-05 the log said only "IntegrityError" for an hour.
    """

    def __init__(self, mode: str, tx_hash: str, cause: Exception) -> None:
        super().__init__(f"{mode} projection stopped at {tx_hash or 'unknown tx'}: {cause}")
        self.mode = mode
        self.tx_hash = tx_hash
        self.cause = cause


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


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def decode_body(body_b64: str) -> dict[str, Any]:
    cells = Cell.one_from_boc(base64.b64decode(body_b64))
    cell = cells[0] if isinstance(cells, list) else cells
    parser = cell.begin_parse()
    opcode = parser.read_uint(32)
    result = {"opcode": opcode, "query_id": parser.read_uint(64)}
    if opcode in {DUEL_OPEN_OFFER, DUEL_OPEN_DIRECT_OFFER, DUEL_ACCEPT_DIRECT_OFFER}:
        result.update(
            offer_id=parser.read_uint(64),
            commitment=parser.read_uint(256),
            chance_bps=parser.read_uint(16),
            total_pool_nano=parser.read_coins(),
            expires_at=parser.read_uint(32),
        )
        if opcode == DUEL_OPEN_OFFER:
            result["counter_offer_id"] = parser.read_uint(64)
        elif opcode == DUEL_OPEN_DIRECT_OFFER:
            result["invite_id"] = parser.read_uint(256)
            result["counter_offer_id"] = 0
        else:
            acceptance = parser.read_ref().begin_parse()
            result.update(
                counter_offer_id=acceptance.read_uint(64),
                direct_valid_until=acceptance.read_uint(32),
                direct_signature=acceptance.read_uint(512),
            )
        # DuelEscrow v1.4 appends an optional holder fee permit. v1.3 bodies
        # simply end here, so the maybe-bit is read only when it exists.
        if len(parser) >= 1 and parser.read_bit():
            permit = parser.read_ref().begin_parse()
            result.update(
                holder_valid_until=permit.read_uint(32),
                holder_signature=permit.read_uint(512),
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
    elif opcode == DUEL_BOOST:
        result.update(
            duel_id=parser.read_uint(64),
            offer_id=parser.read_uint(64),
            amount_nano=parser.read_coins(),
            expected_revision=parser.read_uint(16),
            min_chance_bps=parser.read_uint(16),
            valid_until=parser.read_uint(32),
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
    elif opcode in {BANK_SET_PAUSED, DUEL_SET_PAUSED}:
        result["paused"] = parser.read_uint(1)
    elif opcode in {
        BANK_FUND_RESERVE,
        BANK_WITHDRAW_SURPLUS,
        DUEL_FUND_RESERVE,
        DUEL_WITHDRAW_SURPLUS,
        BANK_ADMIN_WITHDRAWAL,
        DUEL_ADMIN_WITHDRAWAL,
    }:
        result["amount_nano"] = parser.read_coins()
    elif opcode in {BANK_SET_FEE, DUEL_SET_FEE}:
        result["fee_bps"] = parser.read_uint(16)
    elif opcode in {BANK_SET_TREASURY, DUEL_SET_TREASURY}:
        treasury = parser.read_msg_addr()
        result["treasury"] = normalize_address(treasury.to_string(is_user_friendly=False))
    elif opcode in {BANK_SET_OWNER, DUEL_SET_OWNER}:
        owner = parser.read_msg_addr()
        result["owner"] = normalize_address(owner.to_string(is_user_friendly=False))
    return result


async def contract_control(
    db: Any,
    settings: Any,
    mode: str,
) -> ContractControl:
    address = (
        settings.bank_contract_address
        if mode == "bank"
        else settings.effective_duel_contract_address
    )
    key = contract_control_key(mode, settings.ton_network_id, address)
    state = cast(ContractControl | None, await db.get(ContractControl, key))
    if state is not None:
        return state
    owner = normalize_address(settings.control_admin_wallet)
    state = ContractControl(
        key=key,
        mode=mode,
        network=settings.ton_network_id,
        address=normalize_address(address),
        owner=owner,
        treasury=owner,
        fee_bps=settings.bank_fee_bps if mode == "bank" else settings.duel_fee_bps,
    )
    db.add(state)
    await db.flush()
    return state


async def apply_admin_control(
    db: Any,
    state: ContractControl,
    transaction: dict[str, Any],
    decoded: dict[str, Any],
) -> None:
    opcode = decoded["opcode"]
    if opcode in {BANK_SET_PAUSED, DUEL_SET_PAUSED}:
        state.paused = bool(decoded["paused"])
    elif opcode in {BANK_SET_FEE, DUEL_SET_FEE}:
        state.fee_bps = decoded["fee_bps"]
    elif opcode in {BANK_SET_TREASURY, DUEL_SET_TREASURY}:
        state.treasury = decoded["treasury"]
    elif opcode in {BANK_SET_OWNER, DUEL_SET_OWNER}:
        state.owner = decoded["owner"]
    identity = transaction_identity(transaction)
    if identity is None:
        return
    state.last_lt, state.last_tx_hash = identity
    db.add(
        AdminAuditEvent(
            wallet=state.owner,
            action=f"chain.{state.mode}.{opcode:08x}",
            target=state.address,
            payload_json=json.dumps(decoded, separators=(",", ":"), sort_keys=True),
            status="confirmed",
            tx_hash=state.last_tx_hash,
        )
    )


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


async def enqueue_match_notifications(
    db: Any,
    duel: Duel,
    offers: list[MatchmakingOffer],
) -> None:
    for offer in offers:
        if offer.user_id is None:
            continue
        payload = json.dumps(
            {
                "duel_id": duel.id,
                "onchain_duel_id": duel.onchain_duel_id,
                "network": duel.network,
                "offer_id": offer.onchain_offer_id,
                "stake_nano": offer.stake_nano,
                "chance_bps": offer.chance_bps,
                "boost_deadline": (
                    duel.boost_deadline.isoformat() if duel.boost_deadline else None
                ),
                "reveal_deadline": duel.reveal_deadline.isoformat(),
            },
            separators=(",", ":"),
        )
        try:
            async with db.begin_nested():
                db.add(
                    NotificationOutbox(
                        user_id=offer.user_id,
                        kind=KIND_DUEL_MATCHED,
                        dedupe_key=f"duel_matched:{duel.id}:{offer.user_id}",
                        payload_json=payload,
                    )
                )
                await db.flush()
        except IntegrityError:
            continue


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
            state=DuelState.BOOSTING.value,
            boost_deadline=chain_time.replace(microsecond=0) + timedelta(seconds=60),
            hard_deadline=chain_time.replace(microsecond=0) + timedelta(seconds=180),
            reveal_deadline=chain_time.replace(microsecond=0) + timedelta(seconds=360),
            boost_revision=0,
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
        await enqueue_match_notifications(db, duel, ordered)
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
    decoded: dict[str, Any],
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
    control = await contract_control(db, settings, "bank")
    if opcode in BANK_ADMIN_OPCODES:
        await apply_admin_control(db, control, transaction, decoded)
        db.add(
            BankChainEvent(
                network=settings.ton_network_id,
                account=settings.bank_contract_address,
                lt=lt,
                tx_hash=tx_hash,
                event_index=0,
                opcode=opcode,
                payload_json=json.dumps({"in": decoded, "out": outgoing}, separators=(",", ":")),
                applied=True,
            )
        )
        return ProjectionResult.APPLIED
    if opcode != BANK_CREATE_POSITION:
        return ProjectionResult.IGNORED
    incoming = transaction.get("in_msg") or {}
    source = message_address(incoming, "source", "src", "source_address")
    value = message_value(incoming)
    principal = decoded["principal_nano"]
    multiplier = decoded["multiplier_bps"]
    if (
        source is None
        or value is None
        or value < principal + settings.bank_position_gas_nano
        or not settings.bank_min_principal_nano <= principal <= settings.bank_max_principal_nano
        or multiplier not in {12_500, 15_000, 20_000}
    ):
        return ProjectionResult.IGNORED
    verified_wallet = await db.scalar(
        select(Wallet).where(
            Wallet.network == settings.ton_network_id,
            func.lower(Wallet.address) == source.lower(),
        )
    )
    position = await db.scalar(
        select(BankPosition).where(
            BankPosition.network == settings.ton_network_id,
            BankPosition.contract_address == settings.bank_contract_address,
            BankPosition.position_id == decoded["position_id"],
        )
    )
    if position is None:
        target = principal * multiplier // 10_000
        position = BankPosition(
            position_id=decoded["position_id"],
            query_id=decoded["query_id"],
            user_id=verified_wallet.user_id if verified_wallet else None,
            wallet_id=verified_wallet.id if verified_wallet else None,
            owner_wallet=source,
            network=settings.ton_network_id,
            contract_address=settings.bank_contract_address,
            principal_nano=principal,
            multiplier_bps=multiplier,
            target_payout_nano=target,
            remaining_amount_nano=target,
        )
        db.add(position)
        await db.flush()
    elif (
        source != normalize_address(position.owner_wallet)
        or decoded["query_id"] != position.query_id
        or principal != position.principal_nano
        or multiplier != position.multiplier_bps
    ):
        # The identifier was funded outside the API before the local intent.
        # Keep the authoritative public-chain position and detach the stale
        # application intent so it cannot poison all later FIFO projections.
        target = principal * multiplier // 10_000
        position.user_id = verified_wallet.user_id if verified_wallet else None
        position.wallet_id = verified_wallet.id if verified_wallet else None
        position.owner_wallet = source
        position.query_id = decoded["query_id"]
        position.principal_nano = principal
        position.multiplier_bps = multiplier
        position.target_payout_nano = target
        position.funded_amount_nano = 0
        position.remaining_amount_nano = target
        position.failure_reason = "local intent superseded by permissionless on-chain position"

    fee = position.principal_nano * control.fee_bps // 10_000
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
            await create_result_card(
                db,
                user_id=earlier.user_id,
                mode="bank",
                entity_id=earlier.id,
                event_key=f"bank:{earlier.network}:{earlier.id}:{tx_hash}",
                network=earlier.network,
                payout_nano=earlier.target_payout_nano,
                contributed_nano=earlier.principal_nano,
                tx_hash=tx_hash,
            )
            await enqueue_public_feed(
                db,
                settings,
                user_id=earlier.user_id,
                event_kind="bank_payout",
                event_key=f"bank_payout:{earlier.network}:{earlier.id}:{tx_hash}",
                amount_nano=earlier.target_payout_nano,
                result_nano=earlier.target_payout_nano - earlier.principal_nano,
                network=earlier.network,
                tx_hash=tx_hash,
            )
            await qualify_referral(
                db,
                user_id=earlier.user_id,
                owner_wallet=earlier.owner_wallet,
                cause=f"bank:{earlier.position_id}",
                tx_hash=tx_hash,
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
    position.funded_amount_nano = available
    position.remaining_amount_nano = position.target_payout_nano - available
    position.current_status = (
        BankPositionStatus.PARTIALLY_FUNDED.value
        if available > 0
        else BankPositionStatus.QUEUED.value
    )
    position.confirmed_at = datetime.fromtimestamp(int(transaction["now"]), UTC)
    position.funding_transaction = tx_hash
    await accrue_referral_fee_share(db, position=position)
    ahead = await db.scalar(
        select(func.count())
        .select_from(BankPosition)
        .where(
            BankPosition.network == position.network,
            BankPosition.contract_address == position.contract_address,
            BankPosition.current_status.in_(
                [
                    BankPositionStatus.QUEUED.value,
                    BankPositionStatus.PARTIALLY_FUNDED.value,
                ]
            ),
            BankPosition.queue_index.is_not(None),
            BankPosition.queue_index < position.queue_index,
        )
    )
    await create_entry_card(
        db,
        user_id=position.user_id,
        entity_id=position.id,
        event_key=f"bank_entry:{position.network}:{position.id}",
        network=position.network,
        contributed_nano=position.principal_nano,
        queue_position=int(ahead or 0) + 1,
        tx_hash=tx_hash,
    )
    await enqueue_public_feed(
        db,
        settings,
        user_id=position.user_id,
        event_kind="bank_entry",
        event_key=f"bank_entry:{position.network}:{position.id}:{tx_hash}",
        amount_nano=position.principal_nano,
        queue_position=int(ahead or 0) + 1,
        network=position.network,
        tx_hash=tx_hash,
    )
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


# Из десяти процентов комиссии двадцатая часть взноса уходит пригласившему:
# 2% с каждого подтверждённого депозита приведённого человека, навсегда.
REFERRAL_FEE_SHARE_BPS = 200


async def accrue_referral_fee_share(db: Any, *, position: Any) -> None:
    """Credit the inviter with their share of one confirmed deposit.

    Funded by the protocol fee rather than by promises, so a fake account has
    to deposit real money and pay a real fee before anything accrues. The
    position's uuid keys the cause, making the accrual idempotent per deposit
    under the (attribution, cause) unique constraint.
    """
    if position.user_id is None:
        return
    attribution = await db.scalar(
        select(ReferralAttribution).where(
            ReferralAttribution.invitee_user_id == position.user_id,
            ReferralAttribution.status.in_(("pending", "qualified")),
        )
    )
    if attribution is None:
        return
    reward = position.principal_nano * REFERRAL_FEE_SHARE_BPS // 10_000
    if reward <= 0:
        return
    cause = f"fee_share:{position.id}"
    try:
        async with db.begin_nested():
            db.add(
                ReferralReward(
                    attribution_id=attribution.id,
                    cause=cause,
                    reward_points=0,
                    reward_nano=reward,
                )
            )
            await db.flush()
    except IntegrityError:
        pass


async def qualify_referral(
    db: Any,
    *,
    user_id: str | None,
    owner_wallet: str,
    cause: str,
    tx_hash: str,
) -> None:
    """Qualify an invitee after any confirmed BANK or DUEL completion."""
    if user_id is None:
        return
    attribution = await db.scalar(
        select(ReferralAttribution).where(
            ReferralAttribution.invitee_user_id == user_id,
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
    if inviter_wallet and normalize_address(inviter_wallet) == normalize_address(owner_wallet):
        attribution.status = "rejected"
        return
    attribution.status = "qualified"
    attribution.qualified_tx_hash = tx_hash
    attribution.qualified_at = datetime.now(UTC)
    # Until now this only showed up in the profile if you went looking. The
    # person who brought a friend in should hear about it.
    qualified_count = int(
        await db.scalar(
            select(func.count())
            .select_from(ReferralAttribution)
            .where(
                ReferralAttribution.inviter_user_id == attribution.inviter_user_id,
                ReferralAttribution.status == "qualified",
            )
        )
        or 0
    )
    try:
        async with db.begin_nested():
            db.add(
                NotificationOutbox(
                    user_id=attribution.inviter_user_id,
                    kind=KIND_REFERRAL_QUALIFIED,
                    dedupe_key=f"referral:{attribution.id}",
                    payload_json=json.dumps(
                        {"qualified": qualified_count}, separators=(",", ":")
                    ),
                )
            )
            await db.flush()
    except IntegrityError:
        pass
    existing = await db.scalar(
        select(ReferralReward.id).where(
            ReferralReward.attribution_id == attribution.id,
            ReferralReward.cause == cause,
        )
    )
    if existing is None:
        db.add(
            ReferralReward(
                attribution_id=attribution.id,
                cause=cause,
                reward_points=100,
            )
        )


async def apply_duel_transaction(
    db: Any,
    settings: Any,
    transaction: dict[str, Any],
    decoded: dict[str, Any],
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
    control = await contract_control(db, settings, "duel")
    if opcode in DUEL_ADMIN_OPCODES:
        await apply_admin_control(db, control, transaction, decoded)
    incoming = transaction.get("in_msg") or {}
    source = message_address(incoming, "source", "src", "source_address")
    value = message_value(incoming)

    if opcode in {DUEL_OPEN_OFFER, DUEL_OPEN_DIRECT_OFFER, DUEL_ACCEPT_DIRECT_OFFER}:
        offer = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.onchain_offer_id == decoded["offer_id"],
            )
        )
        if (
            source is None
            or value is None
            or decoded["chance_bps"] not in {2500, 5000, 7500}
            or decoded["total_pool_nano"] % 4 != 0
            or not settings.min_pool_nano <= decoded["total_pool_nano"] <= settings.max_pool_nano
        ):
            return ProjectionResult.IGNORED
        stake = decoded["total_pool_nano"] * decoded["chance_bps"] // 10_000
        if value < stake + settings.offer_gas_nano:
            return ProjectionResult.IGNORED
        # The contract accepted this transaction, so any attached holder
        # permit was already signature-checked on chain. The worker still
        # re-verifies with the configured public key: a projection must never
        # trust a fee exemption the backend cannot prove itself. That means
        # repeating the contract's expiry window too, not only the signature,
        # so a misconfigured contract or a wrong success verdict cannot slip an
        # expired exemption into the projection.
        holder_valid_until = decoded.get("holder_valid_until", 0)
        chain_now = int(transaction.get("now") or 0)
        fee_exempt = (
            "holder_signature" in decoded
            and chain_now > 0
            and holder_valid_until >= chain_now
            and holder_valid_until <= chain_now + DUEL_MAX_EXPIRY_DELAY
            and verify_holder_fee_permit(
                settings.duel_invite_public_key,
                f"{decoded['holder_signature']:0128x}",
                network=settings.ton_network_id,
                contract_address=account,
                offer_id=decoded["offer_id"],
                owner_address=source,
                valid_until=holder_valid_until,
            )
        )
        if "holder_signature" in decoded and not fee_exempt:
            return ProjectionResult.RETRY
        if offer is None:
            payout = (
                decoded["total_pool_nano"]
                if fee_exempt
                else decoded["total_pool_nano"]
                - (decoded["total_pool_nano"] * control.fee_bps // 10_000)
            )
            offer = MatchmakingOffer(
                onchain_offer_id=decoded["offer_id"],
                query_id=decoded["query_id"],
                user_id=None,
                wallet_id=None,
                owner_wallet=source,
                network=settings.ton_network_id,
                contract_address=account,
                chance_bps=decoded["chance_bps"],
                total_pool_nano=decoded["total_pool_nano"],
                stake_nano=stake,
                opponent_stake_nano=decoded["total_pool_nano"] - stake,
                fee_bps=control.fee_bps,
                payout_nano=payout,
                commitment_hex=f"{decoded['commitment']:064x}",
                invite_id_hex=(
                    f"{decoded['invite_id']:064x}" if opcode == DUEL_OPEN_DIRECT_OFFER else None
                ),
                counter_offer_id=decoded["counter_offer_id"],
                mode=("external" if opcode == DUEL_OPEN_OFFER else "external_direct"),
                expires_at=datetime.fromtimestamp(decoded["expires_at"], UTC),
            )
            db.add(offer)
            await db.flush()
        elif (
            source != normalize_address(offer.owner_wallet)
            or decoded["query_id"] != offer.query_id
            or decoded["commitment"] != int(offer.commitment_hex, 16)
            or decoded["chance_bps"] != offer.chance_bps
            or decoded["total_pool_nano"] != offer.total_pool_nano
            or decoded["counter_offer_id"] != offer.counter_offer_id
            or decoded.get("invite_id", 0) != int(offer.invite_id_hex or "0", 16)
            or decoded["expires_at"] != int(offer.expires_at.timestamp())
        ):
            payout = (
                decoded["total_pool_nano"]
                if fee_exempt
                else decoded["total_pool_nano"]
                - (decoded["total_pool_nano"] * control.fee_bps // 10_000)
            )
            offer.user_id = None
            offer.wallet_id = None
            offer.owner_wallet = source
            offer.query_id = decoded["query_id"]
            offer.chance_bps = decoded["chance_bps"]
            offer.total_pool_nano = decoded["total_pool_nano"]
            offer.stake_nano = stake
            offer.opponent_stake_nano = decoded["total_pool_nano"] - stake
            offer.fee_bps = control.fee_bps
            offer.payout_nano = payout
            offer.commitment_hex = f"{decoded['commitment']:064x}"
            offer.invite_id_hex = (
                f"{decoded['invite_id']:064x}" if opcode == DUEL_OPEN_DIRECT_OFFER else None
            )
            offer.counter_offer_id = decoded["counter_offer_id"]
            offer.mode = "external" if opcode == DUEL_OPEN_OFFER else "external_direct"
            offer.expires_at = datetime.fromtimestamp(decoded["expires_at"], UTC)
        # The chain is authoritative for the exemption in both directions: a
        # verified permit sets it, and a funding message without one clears a
        # stale local promise, so the payout is recomputed either way. The fee
        # comes from the observed contract configuration rather than the quote:
        # an owner fee change between quote and funding would otherwise project
        # a payout the contract will not send, and the settlement cross-check
        # would then retry that duel forever.
        offer.fee_exempt = fee_exempt
        offer.fee_bps = control.fee_bps
        offer.payout_nano = (
            offer.total_pool_nano
            if fee_exempt
            else offer.total_pool_nano - offer.total_pool_nano * control.fee_bps // 10_000
        )
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
        await enqueue_public_feed(
            db,
            settings,
            user_id=offer.user_id,
            event_kind="duel_entry",
            event_key=f"duel_entry:{offer.network}:{offer.id}:{tx_hash}",
            amount_nano=offer.stake_nano,
            network=offer.network,
            tx_hash=tx_hash,
        )
        if opcode == DUEL_ACCEPT_DIRECT_OFFER:
            counter = await db.scalar(
                select(MatchmakingOffer).where(
                    MatchmakingOffer.network == settings.ton_network_id,
                    MatchmakingOffer.onchain_offer_id == offer.counter_offer_id,
                )
            )
            if (
                counter is None
                or not counter.invite_id_hex
                or counter.state
                not in {
                    OfferState.OPEN.value,
                    OfferState.RESERVED.value,
                }
                or not verify_direct_accept_permit(
                    settings.duel_invite_public_key,
                    f"{decoded['direct_signature']:0128x}",
                    network=settings.ton_network_id,
                    contract_address=account,
                    invite_id_hex=counter.invite_id_hex,
                    counter_offer_id=counter.onchain_offer_id,
                    invited_address=source,
                    valid_until=decoded["direct_valid_until"],
                )
            ):
                return ProjectionResult.RETRY
            challenge = await db.scalar(
                select(DuelChallenge).where(DuelChallenge.creator_offer_id == counter.id)
            )
            if challenge and (
                not challenge.accepted_wallet_address
                or normalize_address(challenge.accepted_wallet_address) != source
            ):
                return ProjectionResult.RETRY
            counter.direct_opponent_wallet = source
            offer.direct_opponent_wallet = counter.owner_wallet
            await create_duel_projection(db, settings, transaction, counter, offer)
        elif opcode == DUEL_OPEN_OFFER and offer.counter_offer_id:
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
                offer.state = OfferState.OPEN.value
            else:
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
            return ProjectionResult.IGNORED
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
    elif opcode == DUEL_BOOST:
        duel = await db.scalar(
            select(Duel).where(
                Duel.network == settings.ton_network_id,
                Duel.onchain_duel_id == decoded["duel_id"],
            )
        )
        offer = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.onchain_offer_id == decoded["offer_id"],
            )
        )
        if (
            duel is None
            or offer is None
            or source is None
            or value is None
            or source != normalize_address(offer.owner_wallet)
            or offer.id not in {duel.offer_a_id, duel.offer_b_id}
            or duel.state != DuelState.BOOSTING.value
            or duel.boost_deadline is None
            or duel.hard_deadline is None
        ):
            return ProjectionResult.RETRY
        chain_time = datetime.fromtimestamp(int(transaction["now"]), UTC).replace(microsecond=0)
        if (
            chain_time > as_utc(duel.boost_deadline)
            or chain_time > as_utc(duel.hard_deadline)
            or chain_time.timestamp() > decoded["valid_until"]
            or decoded["valid_until"] > int(as_utc(duel.hard_deadline).timestamp())
            or decoded["expected_revision"] != duel.boost_revision
            or decoded["amount_nano"] < 100_000_000
            or value < decoded["amount_nano"] + 50_000_000
        ):
            return ProjectionResult.RETRY
        first = await db.get(MatchmakingOffer, duel.offer_a_id)
        second = await db.get(MatchmakingOffer, duel.offer_b_id)
        if first is None or second is None:
            return ProjectionResult.RETRY
        if offer.id == first.id:
            first.stake_nano += decoded["amount_nano"]
        else:
            second.stake_nano += decoded["amount_nano"]
        total_pool = first.stake_nano + second.stake_nano
        chance_a = first.stake_nano * 10_000 // total_pool
        chance_b = 10_000 - chance_a
        boosted_chance = chance_a if offer.id == first.id else chance_b
        if (
            total_pool > 100_000_000_000
            or chance_a < 1_000
            or chance_a > 9_000
            or chance_b < 1_000
            or chance_b > 9_000
            or boosted_chance < decoded["min_chance_bps"]
        ):
            return ProjectionResult.RETRY
        # The winner-if-won payout is per offer: an exempt holder keeps the
        # full pool while the other side still pays the protocol fee.
        fee = total_pool * first.fee_bps // 10_000
        first.chance_bps = chance_a
        first.total_pool_nano = total_pool
        first.opponent_stake_nano = second.stake_nano
        first.payout_nano = total_pool if first.fee_exempt else total_pool - fee
        second.chance_bps = chance_b
        second.total_pool_nano = total_pool
        second.opponent_stake_nano = first.stake_nano
        second.payout_nano = total_pool if second.fee_exempt else total_pool - fee
        duel.boost_revision += 1
        extended_deadline = chain_time + timedelta(seconds=20)
        if extended_deadline > as_utc(duel.boost_deadline):
            duel.boost_deadline = min(extended_deadline, as_utc(duel.hard_deadline))
            duel.reveal_deadline = duel.boost_deadline + timedelta(seconds=300)
        players = (await db.scalars(select(DuelPlayer).where(DuelPlayer.duel_id == duel.id))).all()
        for player in players:
            projected = first if player.offer_id == first.id else second
            player.chance_bps = projected.chance_bps
            player.stake_nano = projected.stake_nano
        db.add(
            DuelBoost(
                duel_id=duel.id,
                offer_id=offer.id,
                network=settings.ton_network_id,
                query_id=decoded["query_id"],
                revision=duel.boost_revision,
                amount_nano=decoded["amount_nano"],
                chance_a_bps=chance_a,
                chance_b_bps=chance_b,
                tx_hash=tx_hash,
                created_at=chain_time,
            )
        )
    elif opcode == DUEL_REVEAL:
        offer = await db.scalar(
            select(MatchmakingOffer).where(
                MatchmakingOffer.network == settings.ton_network_id,
                MatchmakingOffer.onchain_offer_id == decoded["offer_id"],
            )
        )
        if offer is None or source != normalize_address(offer.owner_wallet):
            return ProjectionResult.IGNORED
        duel = await db.scalar(
            select(Duel).where(
                Duel.network == settings.ton_network_id,
                Duel.onchain_duel_id == decoded["duel_id"],
            )
        )
        chain_time = datetime.fromtimestamp(int(transaction["now"]), UTC)
        if (
            duel is None
            or offer.id not in {duel.offer_a_id, duel.offer_b_id}
            or (duel.boost_deadline is not None and chain_time <= as_utc(duel.boost_deadline))
        ):
            return ProjectionResult.RETRY
        offer.revealed = True
        if await db.scalar(select(DuelReveal.id).where(DuelReveal.offer_id == offer.id)) is None:
            duel.state = DuelState.REVEALING.value
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
            continue
        if (
            refund.get("destination") != normalize_address(offer.owner_wallet)
            or refund.get("value_nano") != offer.stake_nano
        ):
            return ProjectionResult.RETRY
        offer.state = OfferState.REFUNDED.value
    if opcode == DUEL_EXPIRE_DUEL and refunds and not payouts:
        # A no-reveal ExpireDuel refunds both stakes and is terminal on chain.
        # Leaving the duel in `revealing` would keep it forever overdue in
        # monitoring. No DuelSettlement row is written: a refund is not a
        # completed duel and must not earn the settlement rating points.
        duel = await db.scalar(
            select(Duel).where(
                Duel.network == settings.ton_network_id,
                Duel.onchain_duel_id == decoded["duel_id"],
            )
        )
        if duel is not None:
            duel.state = DuelState.REFUNDED.value
            duel.settled_tx_hash = tx_hash
            duel.settled_at = datetime.fromtimestamp(int(transaction["now"]), UTC)
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
            continue
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
        await create_result_card(
            db,
            user_id=winner.user_id,
            mode="duel",
            entity_id=duel.id,
            event_key=f"duel:{winner.network}:{duel.id}:{tx_hash}",
            network=winner.network,
            payout_nano=winner.payout_nano,
            contributed_nano=winner.stake_nano,
            tx_hash=tx_hash,
        )
        await enqueue_public_feed(
            db,
            settings,
            user_id=winner.user_id,
            event_kind="duel_payout",
            event_key=f"duel_payout:{winner.network}:{duel.id}:{tx_hash}",
            amount_nano=winner.payout_nano,
            result_nano=winner.payout_nano - winner.stake_nano,
            network=winner.network,
            tx_hash=tx_hash,
        )
        for player in (first, second):
            await qualify_referral(
                db,
                user_id=player.user_id,
                owner_wallet=player.owner_wallet,
                cause=f"duel:{duel.onchain_duel_id}",
                tx_hash=tx_hash,
            )

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


async def warn_unrevealed_duels(db: AsyncSession) -> None:
    """One last call before a duel expires unplayed.

    Missing the reveal window is not a loss — both stakes go back and the match
    is void, which is worse than either outcome. The warning goes out with a
    minute or so left, and only to players who have not revealed yet.
    """
    now = datetime.now(UTC)
    duels = (
        await db.scalars(
            select(Duel).where(
                Duel.state == "revealing",
                Duel.reveal_deadline > now,
                Duel.reveal_deadline < now + timedelta(seconds=90),
            )
        )
    ).all()
    for duel in duels:
        revealed = set(
            await db.scalars(select(DuelReveal.offer_id).where(DuelReveal.duel_id == duel.id))
        )
        players = (
            await db.scalars(select(DuelPlayer).where(DuelPlayer.duel_id == duel.id))
        ).all()
        for player in players:
            if player.user_id is None or player.offer_id in revealed:
                continue
            payload = json.dumps(
                {"duel_id": duel.id, "reveal_deadline": duel.reveal_deadline.isoformat()},
                separators=(",", ":"),
            )
            try:
                async with db.begin_nested():
                    db.add(
                        NotificationOutbox(
                            user_id=player.user_id,
                            kind=KIND_DUEL_REVEAL_SOON,
                            dedupe_key=f"reveal_soon:{duel.id}:{player.user_id}",
                            payload_json=payload,
                        )
                    )
                    await db.flush()
            except IntegrityError:
                continue


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
        return ProjectionResult.IGNORED
    try:
        decoded = decode_body(body)
    except Exception:
        return ProjectionResult.IGNORED
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
) -> tuple[int, bool]:
    if not address:
        return 0, False
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
    blocked = False
    failure: ProjectionFailure | None = None
    async with session_factory() as db:
        checkpoint = await db.get(ChainCheckpoint, key) or ChainCheckpoint(key=key, last_lt=0)
        db.add(checkpoint)
        for transaction in transactions:
            if not has_masterchain_finality(transaction):
                break
            savepoint = await db.begin_nested()
            try:
                result = await apply_transaction(db, settings, transaction, mode)
            except Exception as exc:
                # Stop here rather than skip: a later transaction may depend on
                # this one, and projecting it out of order would be a quieter,
                # worse failure than standing still. What already applied is
                # kept, so the next cycle resumes at this transaction instead
                # of replaying — and dying on — the whole batch again.
                await savepoint.rollback()
                failure = ProjectionFailure(mode, transaction.get("hash", ""), exc)
                blocked = True
                break
            if result == ProjectionResult.RETRY:
                await savepoint.rollback()
                blocked = True
                break
            await savepoint.commit()
            if result == ProjectionResult.APPLIED:
                applied += 1
            checkpoint.last_lt = max(checkpoint.last_lt, int(transaction["lt"]) + 1)
        if not blocked:
            checkpoint.heartbeat_at = datetime.now(UTC)
        await db.execute(
            update(BankPosition)
            .where(
                BankPosition.current_status == BankPositionStatus.PENDING_CONFIRMATION.value,
                # Matches the quote's five-minute signing window plus grace.
                BankPosition.created_at < datetime.now(UTC) - timedelta(minutes=6),
            )
            .values(
                current_status=BankPositionStatus.FAILED.value,
                failure_reason="funding intent expired before on-chain confirmation",
            )
        )
        await warn_unrevealed_duels(db)
        await db.execute(
            update(MatchmakingOffer)
            .where(
                MatchmakingOffer.state == OfferState.PENDING_FUNDING.value,
                MatchmakingOffer.expires_at < datetime.now(UTC),
            )
            .values(state=OfferState.EXPIRED.value)
        )
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
    if failure is not None:
        raise failure
    return applied, blocked


async def run_once(http: httpx.AsyncClient, session_factory: Any, settings: Any) -> int:
    # The two contracts share nothing but this loop, so one must not be able to
    # stop the other. BANK ran first and raised, and for an hour on launch night
    # no duel was settled either — for a reason that had nothing to do with
    # duels. Each is attempted on its own; the trouble is reported afterwards.
    applied = 0
    blocked = False
    trouble: list[Exception] = []
    for mode, address in (
        ("bank", settings.bank_contract_address),
        ("duel", settings.effective_duel_contract_address),
    ):
        try:
            count, contract_blocked = await run_contract_once(
                http,
                session_factory,
                settings,
                mode=mode,
                address=address,
            )
        except Exception as exc:
            logger.error(
                "chain_projection_stopped",
                mode=mode,
                error=type(exc).__name__,
                detail=str(exc),
                tx_hash=getattr(exc, "tx_hash", None),
                exc_info=exc,
            )
            trouble.append(exc)
            continue
        applied += count
        blocked = blocked or contract_blocked
    if trouble:
        raise trouble[0]
    if blocked:
        raise RuntimeError("chain projection is blocked on incomplete authoritative data")
    await asyncio.to_thread(
        HEARTBEAT_FILE.write_text,
        str(int(datetime.now(UTC).timestamp())),
        encoding="utf-8",
    )
    return applied


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
        retry_delay = 5
        consecutive_failures = 0
        reported = False
        while True:
            try:
                await run_once(http, session_factory, settings)
                retry_delay = 5
                consecutive_failures = 0
                if reported:
                    reported = False
                    await announce(http, settings, "✅ Чтение цепи восстановлено.")
            except Exception as exc:
                # The class name alone sent a whole outage to the Postgres log
                # to be diagnosed. Say what happened and where.
                logger.error(
                    "chain_worker_failed",
                    error=type(exc).__name__,
                    detail=str(exc),
                    exc_info=exc,
                )
                consecutive_failures += 1
                retry_delay = min(retry_delay * 2, 60)
                # One failure can be a provider hiccup; three in a row is the
                # queue standing still while deposits keep arriving. Say it
                # once, not every minute for an hour.
                if consecutive_failures >= ALERT_AFTER_FAILURES and not reported:
                    reported = True
                    await announce(
                        http,
                        settings,
                        "🛑 Воркер перестал читать цепь.\n\n"
                        f"{type(exc).__name__}: {exc}\n\n"
                        "Взносы и ставки сейчас не подтверждаются.",
                    )
            await asyncio.sleep(retry_delay)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
