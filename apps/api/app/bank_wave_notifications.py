from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from .config import Settings
from .models import NotificationOutbox, User
from .modules.bank.models import BankPosition
from .modules.bank.wave import bank_wave_view, wave_window
from .ton import normalize_address

KIND_BANK_WAVE = "bank_wave"


async def ensure_bank_wave_notifications(
    session_factory: Any,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    """Materialise one weekly event into the durable Telegram outbox.

    The outbox dedupe key is the event id plus the exact moment, so a worker
    restart cannot announce the same Wave twice.
    """

    if not settings.bank_wave_enabled:
        return 0
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    starts_at, ends_at = wave_window(current, settings)
    event_id = starts_at.date().isoformat()
    queued = 0

    async with session_factory() as db:
        wave = await bank_wave_view(db, settings, now=current)
        if wave is None:
            return 0
        # Schedule the opening while it is still useful. If the notifier was
        # down for the whole event, nobody receives a stale "started" message.
        if current < ends_at:
            users = (
                await db.scalars(select(User).where(User.result_notifications_enabled.is_(True)))
            ).all()
            for user in users:
                queued += await _enqueue(
                    db,
                    user_id=user.id,
                    dedupe_key=f"bank_wave:{event_id}:start:{user.id}",
                    next_attempt_at=max(starts_at, current),
                    payload={"event": "start", "goal": settings.bank_wave_goal},
                )

        if (
            settings.bank_wave_operator_telegram_id
            and wave.state in {"goal_reached", "awaiting_boost"}
            and not wave.boost_confirmed
        ):
            operator = await db.scalar(
                select(User).where(User.telegram_id == settings.bank_wave_operator_telegram_id)
            )
            if operator is not None:
                queued += await _enqueue(
                    db,
                    user_id=operator.id,
                    dedupe_key=f"bank_wave:{event_id}:operator:{operator.id}",
                    next_attempt_at=current,
                    payload={"event": "operator", "boost_nano": wave.boost_nano},
                )

        if wave.state == "completed":
            entrants = (
                select(
                    BankPosition.user_id.label("user_id"),
                    func.min(BankPosition.confirmed_at).label("joined_at"),
                )
                .where(
                    BankPosition.network == settings.ton_network_id,
                    BankPosition.contract_address == settings.bank_contract_address,
                    BankPosition.user_id.is_not(None),
                    BankPosition.confirmed_at >= starts_at,
                    BankPosition.confirmed_at < ends_at,
                    func.lower(BankPosition.owner_wallet)
                    != normalize_address(settings.bank_wave_wallet).lower(),
                )
                .group_by(BankPosition.user_id)
                .subquery()
            )
            rows = (
                await db.execute(
                    select(User, entrants.c.joined_at)
                    .join(entrants, entrants.c.user_id == User.id)
                    .where(User.result_notifications_enabled.is_(True))
                    .order_by(entrants.c.joined_at, User.id)
                )
            ).all()
            for user, _joined_at in rows:
                queued += await _enqueue(
                    db,
                    user_id=user.id,
                    dedupe_key=f"bank_wave:{event_id}:closed:{user.id}",
                    next_attempt_at=current,
                    payload={
                        "event": "closed",
                        "goal": wave.goal,
                        "boost_nano": wave.boost_nano,
                        "proof_url": wave.proof_url,
                    },
                )
            if rows:
                closer = rows[-1][0]
                queued += await _enqueue(
                    db,
                    user_id=closer.id,
                    dedupe_key=f"bank_wave:{event_id}:closer:{closer.id}",
                    next_attempt_at=current,
                    payload={"event": "closer", "goal": wave.goal},
                )
        await db.commit()
    return queued


async def _enqueue(
    db: Any,
    *,
    user_id: str,
    dedupe_key: str,
    next_attempt_at: datetime,
    payload: dict[str, object],
) -> int:
    exists = await db.scalar(
        select(NotificationOutbox.id).where(NotificationOutbox.dedupe_key == dedupe_key)
    )
    if exists:
        return 0
    db.add(
        NotificationOutbox(
            user_id=user_id,
            kind=KIND_BANK_WAVE,
            dedupe_key=dedupe_key,
            payload_json=json.dumps(payload, separators=(",", ":")),
            next_attempt_at=next_attempt_at,
        )
    )
    return 1


def bank_wave_text(payload: dict[str, object]) -> str:
    event = str(payload.get("event", ""))
    if event == "start":
        return (
            "<b>Волна началась.</b>\n\n"
            "До 20:30 по Москве. Войдут 8 человек — LOOP добавит 5 GRAM в BANK."
        )
    if event == "closer":
        return "<b>Ты закрыл Волну.</b>\n\nВосемь участников вошли. Твой ход стал последним."
    if event == "operator":
        return (
            "<b>Волна собрана.</b>\n\n"
            "Открой BANK с кошельком LOOP и создай позицию на 5 GRAM. "
            "Результат появится только после подтверждения сети."
        )
    return (
        "<b>Волна закрыта.</b>\n\nВосемь участников вошли. Взнос LOOP на 5 GRAM подтверждён в BANK."
    )
