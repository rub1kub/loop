from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    BankCycle,
    CycleEvent,
    CycleEventKind,
    CycleStatus,
    ProofType,
    User,
)

CYCLE_DURATION = timedelta(days=7)
DEFAULT_CYCLE_GOAL = 6


class ActiveCycleExistsError(RuntimeError):
    pass


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def progress_bps(cycle: BankCycle) -> int:
    return min(cycle.event_count * 10_000 // max(cycle.goal_events, 1), 10_000)


def expire_if_needed(cycle: BankCycle, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if cycle.status != CycleStatus.ACTIVE.value or as_utc(cycle.ends_at) > current:
        return False
    cycle.status = CycleStatus.EXPIRED.value
    cycle.completed_at = current
    cycle.updated_at = current
    return True


async def latest_cycle(db: AsyncSession, user_id: str) -> BankCycle | None:
    cycle = await db.scalar(
        select(BankCycle)
        .where(BankCycle.user_id == user_id)
        .order_by(BankCycle.sequence_number.desc())
        .limit(1)
    )
    if cycle is not None:
        expire_if_needed(cycle)
    return cycle


async def start_cycle(
    db: AsyncSession, user: User, goal_events: int = DEFAULT_CYCLE_GOAL
) -> BankCycle:
    await db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    active = await db.scalar(
        select(BankCycle)
        .where(BankCycle.user_id == user.id, BankCycle.status == CycleStatus.ACTIVE.value)
        .with_for_update()
    )
    if active is not None and not expire_if_needed(active):
        raise ActiveCycleExistsError
    if active is not None:
        await db.flush()

    sequence = (
        await db.scalar(
            select(func.max(BankCycle.sequence_number)).where(BankCycle.user_id == user.id)
        )
        or 0
    ) + 1
    now = datetime.now(UTC)
    cycle = BankCycle(
        user_id=user.id,
        sequence_number=sequence,
        goal_events=goal_events,
        event_count=1,
        started_at=now,
        ends_at=now + CYCLE_DURATION,
    )
    db.add(cycle)
    await db.flush()
    db.add(
        CycleEvent(
            cycle_id=cycle.id,
            user_id=user.id,
            actor_user_id=user.id,
            kind=CycleEventKind.CYCLE_STARTED.value,
            title="Цикл начат",
            proof_type=ProofType.SYSTEM.value,
            proof_ref=cycle.id,
            dedupe_key="cycle-started",
        )
    )
    await db.flush()
    return cycle


async def record_cycle_event(
    db: AsyncSession,
    *,
    user_id: str,
    kind: CycleEventKind,
    title: str,
    proof_type: ProofType,
    dedupe_key: str,
    proof_ref: str | None = None,
    actor_user_id: str | None = None,
) -> CycleEvent | None:
    cycle = await db.scalar(
        select(BankCycle)
        .where(BankCycle.user_id == user_id, BankCycle.status == CycleStatus.ACTIVE.value)
        .with_for_update()
    )
    if cycle is None or expire_if_needed(cycle):
        return None
    existing = await db.scalar(
        select(CycleEvent).where(
            CycleEvent.cycle_id == cycle.id,
            CycleEvent.dedupe_key == dedupe_key,
        )
    )
    if existing is not None:
        return existing

    event = CycleEvent(
        cycle_id=cycle.id,
        user_id=user_id,
        actor_user_id=actor_user_id,
        kind=kind.value,
        title=title[:160],
        proof_type=proof_type.value,
        proof_ref=proof_ref,
        dedupe_key=dedupe_key[:192],
    )
    db.add(event)
    cycle.event_count += 1
    cycle.updated_at = datetime.now(UTC)
    if cycle.event_count >= cycle.goal_events:
        cycle.status = CycleStatus.COMPLETED.value
        cycle.completed_at = cycle.updated_at
    await db.flush()
    return event


async def cycle_events(
    db: AsyncSession, user_id: str, cycle_id: str, limit: int = 20
) -> list[CycleEvent]:
    return list(
        (
            await db.scalars(
                select(CycleEvent)
                .where(CycleEvent.user_id == user_id, CycleEvent.cycle_id == cycle_id)
                .order_by(CycleEvent.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
