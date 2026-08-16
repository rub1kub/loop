from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from ...config import Settings
from ...models import User
from ...schemas import BankWaveView
from ...ton import explorer_transaction_url, normalize_address
from .models import BankPosition

MOSCOW = ZoneInfo("Europe/Moscow")
RESULT_HOLD = timedelta(hours=24)
LAST_MOVE_EVENT_ID = "2026-08-16"
LAST_MOVE_SILENCE = timedelta(minutes=30)


def wave_window(now: datetime, settings: Settings) -> tuple[datetime, datetime]:
    """Return the one event the product should show: live/recent, otherwise next."""

    current = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    local = current.astimezone(MOSCOW)
    days_since = (local.weekday() - settings.bank_wave_weekday) % 7
    candidate_day = local.date() - timedelta(days=days_since)
    candidate = datetime.combine(
        candidate_day,
        time(settings.bank_wave_hour_moscow),
        tzinfo=MOSCOW,
    )
    if candidate > local:
        candidate -= timedelta(days=7)
    candidate_end = candidate + timedelta(minutes=settings.bank_wave_duration_minutes)
    if candidate <= local < candidate_end + RESULT_HOLD:
        start = candidate
    else:
        start = candidate + timedelta(days=7)
    end = start + timedelta(minutes=settings.bank_wave_duration_minutes)
    return start.astimezone(UTC), end.astimezone(UTC)


async def bank_wave_view(
    db: Any,
    settings: Settings,
    *,
    user_id: str | None = None,
    now: datetime | None = None,
) -> BankWaveView | None:
    if not settings.bank_wave_enabled:
        return None
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    starts_at, ends_at = wave_window(current, settings)
    # The public operator address is configuration, never user input. Refuse a
    # bad value at startup instead of making the five-second BANK pulse fail.
    project_wallet = normalize_address(settings.bank_wave_wallet)
    entries = (
        select(
            BankPosition.user_id.label("user_id"),
            func.min(BankPosition.confirmed_at).label("joined_at"),
        )
        .where(
            BankPosition.network == settings.ton_network_id,
            BankPosition.contract_address == settings.bank_contract_address,
            BankPosition.user_id.is_not(None),
            BankPosition.confirmed_at.is_not(None),
            BankPosition.confirmed_at >= starts_at,
            BankPosition.confirmed_at < ends_at,
            func.lower(BankPosition.owner_wallet) != project_wallet.lower(),
        )
        .group_by(BankPosition.user_id)
        .subquery()
    )
    participants = int(await db.scalar(select(func.count()).select_from(entries)) or 0)
    goal_reached = participants >= settings.bank_wave_goal

    last_move_deadline: datetime | None = None
    if starts_at.astimezone(MOSCOW).date().isoformat() == LAST_MOVE_EVENT_ID:
        confirmations = (
            await db.scalars(
                select(BankPosition.confirmed_at)
                .where(
                    BankPosition.network == settings.ton_network_id,
                    BankPosition.contract_address == settings.bank_contract_address,
                    BankPosition.user_id.is_not(None),
                    BankPosition.confirmed_at.is_not(None),
                    BankPosition.confirmed_at >= starts_at,
                    func.lower(BankPosition.owner_wallet) != project_wallet.lower(),
                )
                .order_by(BankPosition.confirmed_at, BankPosition.position_id)
            )
        ).all()
        # Stop at the first 30-minute quiet period. Deposits made after the
        # event has already closed cannot silently restart it on another day.
        for confirmed_at in confirmations:
            if confirmed_at is None:
                continue
            if confirmed_at.tzinfo is None:
                confirmed_at = confirmed_at.replace(tzinfo=UTC)
            if last_move_deadline is not None and confirmed_at >= last_move_deadline:
                break
            last_move_deadline = confirmed_at + LAST_MOVE_SILENCE

    closer_user_id: str | None = None
    closer_name: str | None = None
    closer_username: str | None = None
    if goal_reached and current >= ends_at:
        closer = await db.execute(
            select(User.id, User.first_name, User.username)
            .join(entries, entries.c.user_id == User.id)
            .order_by(entries.c.joined_at.desc(), User.id)
            .limit(1)
        )
        row = closer.one_or_none()
        if row is not None:
            closer_user_id, closer_name, closer_username = row

    boost_filters = (
        BankPosition.network == settings.ton_network_id,
        BankPosition.contract_address == settings.bank_contract_address,
        func.lower(BankPosition.owner_wallet) == project_wallet.lower(),
        BankPosition.principal_nano == settings.bank_wave_boost_nano,
        BankPosition.confirmed_at.is_not(None),
    )
    boost = await db.scalar(
        select(BankPosition)
        .where(
            *boost_filters,
            BankPosition.confirmed_at >= starts_at,
            BankPosition.confirmed_at <= ends_at + RESULT_HOLD,
        )
        .order_by(BankPosition.confirmed_at)
        .limit(1)
    )
    campaign_start = settings.bank_wave_campaign_starts_at
    if campaign_start is not None and campaign_start.tzinfo is None:
        campaign_start = campaign_start.replace(tzinfo=UTC)
    used_filters = list(boost_filters)
    if campaign_start is not None:
        used_filters.append(BankPosition.confirmed_at >= campaign_start)
    boosts_used = int(
        await db.scalar(select(func.count()).select_from(BankPosition).where(*used_filters)) or 0
    )
    # A completed fourth Wave remains visible for the result hold. Only the
    # next, unfunded week disappears, so the product never promises a fifth
    # 5 GRAM position outside the agreed 20 GRAM campaign budget.
    if boosts_used >= settings.bank_wave_max_boosts and boost is None:
        return None
    boost_confirmed = boost is not None and boost.funding_transaction is not None
    proof_url = (
        explorer_transaction_url(settings.ton_network_id, boost.funding_transaction)
        if boost_confirmed and boost is not None
        else None
    )

    if current < starts_at:
        state = "upcoming"
    elif current < ends_at:
        state = "goal_reached" if goal_reached else "active"
    elif not goal_reached:
        state = "missed"
    elif boost_confirmed:
        state = "completed"
    else:
        state = "awaiting_boost"

    return BankWaveView(
        id=starts_at.astimezone(MOSCOW).date().isoformat(),
        state=state,
        starts_at=starts_at,
        ends_at=ends_at,
        participants=participants,
        goal=settings.bank_wave_goal,
        boost_nano=settings.bank_wave_boost_nano,
        boost_confirmed=boost_confirmed,
        proof_url=proof_url,
        closer_name=closer_name,
        closer_username=closer_username,
        is_closer=closer_user_id is not None and closer_user_id == user_id,
        last_move_deadline=last_move_deadline,
    )
