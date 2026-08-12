from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime, time, timedelta
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import NotificationOutbox, User
from .modules.bank.models import BankPosition
from .modules.bank.pulse import QUEUE_STATES, bank_queue_pulse
from .modules.teams.models import TeamMembership, TeamScoreEvent

logger = structlog.get_logger()

KIND_BANK_MOMENTUM = "bank_momentum"
MOSCOW = ZoneInfo("Europe/Moscow")
ACTIVE_POSITION_STATES = QUEUE_STATES
TEAMMATE_SIGNAL_MAX_AGE = timedelta(minutes=30)


def moscow_day_start(now: datetime) -> datetime:
    current = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    local = current.astimezone(MOSCOW)
    return datetime.combine(local.date(), time.min, tzinfo=MOSCOW).astimezone(UTC)


def moscow_day_key(now: datetime) -> str:
    current = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return current.astimezone(MOSCOW).date().isoformat()


async def enqueue_bank_momentum(
    db: AsyncSession,
    *,
    user_ids: Iterable[str],
    event_key: str,
    payload: dict[str, object],
    now: datetime,
) -> int:
    """Queue at most one timely BANK nudge per person and Moscow day.

    The event itself remains uniquely keyed as well. The daily cap includes
    pending and failed deliveries: a transport problem must not turn one
    product event into repeated pressure.
    """

    recipients = tuple(dict.fromkeys(user_ids))
    if not recipients:
        return 0
    eligible = set(
        await db.scalars(
            select(User.id).where(
                User.id.in_(recipients),
                User.result_notifications_enabled.is_(True),
            )
        )
    )
    if not eligible:
        return 0
    used_today = set(
        await db.scalars(
            select(NotificationOutbox.user_id)
            .where(
                NotificationOutbox.kind == KIND_BANK_MOMENTUM,
                NotificationOutbox.user_id.in_(eligible),
                NotificationOutbox.created_at >= moscow_day_start(now),
            )
            .distinct()
        )
    )
    available = eligible - used_today
    if not available:
        return 0
    keys = {
        user_id: f"bank_momentum:{moscow_day_key(now)}:{user_id}" for user_id in available
    }
    existing = set(
        await db.scalars(
            select(NotificationOutbox.dedupe_key).where(
                NotificationOutbox.dedupe_key.in_(tuple(keys.values()))
            )
        )
    )
    encoded = json.dumps(
        {**payload, "source": event_key},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    queued = 0
    for user_id, dedupe_key in keys.items():
        if dedupe_key in existing:
            continue
        try:
            async with db.begin_nested():
                db.add(
                    NotificationOutbox(
                        user_id=user_id,
                        kind=KIND_BANK_MOMENTUM,
                        dedupe_key=dedupe_key,
                        payload_json=encoded,
                        next_attempt_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
                await db.flush()
        except IntegrityError:
            continue
        queued += 1
    return queued


async def enqueue_teammate_entry_notifications(
    db: AsyncSession,
    *,
    position: BankPosition,
    now: datetime | None = None,
) -> int:
    if position.user_id is None or position.confirmed_at is None:
        return 0
    delivery_at = now or datetime.now(UTC)
    confirmed_at = position.confirmed_at
    if confirmed_at.tzinfo is None:
        confirmed_at = confirmed_at.replace(tzinfo=UTC)
    if delivery_at - confirmed_at > TEAMMATE_SIGNAL_MAX_AGE:
        return 0
    score = await db.scalar(
        select(TeamScoreEvent).where(
            TeamScoreEvent.source_key == f"bank_entry:{position.network}:{position.id}"
        )
    )
    if score is None:
        return 0
    recipients = (
        await db.scalars(
            select(TeamMembership.user_id).where(
                TeamMembership.team_id == score.team_id,
                TeamMembership.state == "active",
                TeamMembership.user_id != position.user_id,
            )
        )
    ).all()
    entrant = await db.get(User, position.user_id)
    name = (
        entrant.first_name.strip()
        if entrant and entrant.first_name.strip()
        else "Участник команды"
    )
    return await enqueue_bank_momentum(
        db,
        user_ids=recipients,
        event_key=f"team_entry:{position.network}:{position.id}",
        payload={"event": "teammate_joined", "name": name},
        now=delivery_at,
    )


async def enqueue_payout_ready_notifications(
    db: AsyncSession,
    settings: Settings,
    *,
    exclude_user_id: str | None,
    now: datetime,
) -> int:
    pulse = await bank_queue_pulse(db, settings)
    if pulse.minimum_entry_payouts <= 0:
        return 0
    head = await db.scalar(
        select(BankPosition)
        .where(
            BankPosition.network == settings.ton_network_id,
            BankPosition.contract_address == settings.bank_contract_address,
            BankPosition.current_status.in_(ACTIVE_POSITION_STATES),
            BankPosition.queue_index.is_not(None),
        )
        .order_by(BankPosition.queue_index, BankPosition.confirmed_at, BankPosition.position_id)
        .limit(1)
    )
    if head is None:
        return 0
    active_users = select(BankPosition.user_id).where(
        BankPosition.network == settings.ton_network_id,
        BankPosition.contract_address == settings.bank_contract_address,
        BankPosition.current_status.in_(ACTIVE_POSITION_STATES),
        BankPosition.user_id.is_not(None),
    )
    previous_entrants = select(BankPosition.user_id).where(
        BankPosition.network == settings.ton_network_id,
        BankPosition.contract_address == settings.bank_contract_address,
        BankPosition.confirmed_at.is_not(None),
        BankPosition.user_id.is_not(None),
    )
    # This is a return signal, not a cold broadcast to everyone who once
    # opened the Mini App. Only confirmed previous BANK participants without a
    # position currently in flight are relevant recipients.
    recipients_query = select(User.id).where(
        User.id.in_(previous_entrants),
        User.id.not_in(active_users),
    )
    if exclude_user_id is not None:
        recipients_query = recipients_query.where(User.id != exclude_user_id)
    recipients = (await db.scalars(recipients_query)).all()
    return await enqueue_bank_momentum(
        db,
        user_ids=recipients,
        event_key=f"payout_ready:{settings.ton_network_id}:{head.id}",
        payload={
            "event": "payout_ready",
            "positions": pulse.minimum_entry_payouts,
        },
        now=now,
    )


async def enqueue_confirmed_entry_momentum_safely(
    db: AsyncSession,
    settings: Settings,
    *,
    position: BankPosition,
) -> None:
    """Social notifications are rebuildable and never block chain indexing."""

    try:
        now = datetime.now(UTC)
        async with db.begin_nested():
            await enqueue_teammate_entry_notifications(db, position=position, now=now)
            await enqueue_payout_ready_notifications(
                db,
                settings,
                exclude_user_id=position.user_id,
                now=now,
            )
    except Exception as exc:  # noqa: BLE001 - financial projection must continue
        logger.warning(
            "bank_momentum_enqueue_failed",
            position_id=position.id,
            error=type(exc).__name__,
            detail=str(exc),
        )


def bank_momentum_text(payload: dict[str, Any]) -> str:
    event = str(payload.get("event", ""))
    if event == "wave_near":
        remaining = max(1, int(payload.get("remaining", 1)))
        suffix = "человек" if remaining == 1 else "человека"
        return f"<b>Волна почти собрана.</b>\n\nОсталось {remaining} {suffix}."
    if event == "teammate_joined":
        name = escape(str(payload.get("name", "Участник команды")))
        return f"<b>{name} сейчас в BANK.</b>\n\nТвоя команда движется."
    positions = max(1, int(payload.get("positions", 1)))
    if positions == 1:
        return "<b>Сейчас очередь двигается.</b>\n\nСледующий вход закроет ближайшую позицию."
    return (
        f"<b>Сейчас очередь двигается.</b>\n\n"
        f"Следующий вход закроет {positions} {_positions_word(positions)}."
    )


def _positions_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "позицию"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "позиции"
    return "позиций"
