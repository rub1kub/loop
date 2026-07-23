from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from .models import ReferralAttribution, User
from .modules.bank.models import BankPayout, BankPosition, BankPositionStatus
from .modules.duel.models import (
    Duel,
    DuelOffer,
    DuelPlayer,
    DuelReveal,
    DuelSettlement,
    OfferState,
)
from .schemas import (
    RatingEntryView,
    RatingFormulaItem,
    RatingPulseView,
    RatingView,
)

BANK_PAYOUT_POINTS = 100
DUEL_SETTLEMENT_POINTS = 60
TIMELY_REVEAL_POINTS = 20
QUALIFIED_REFERRAL_POINTS = 25
MISSED_REVEAL_POINTS = -40

RATING_FORMULA = [
    RatingFormulaItem(
        code="bank_payout",
        label="Выплата BANK с on-chain proof",
        points=BANK_PAYOUT_POINTS,
    ),
    RatingFormulaItem(
        code="duel_settlement",
        label="Завершённый DUEL с on-chain proof",
        points=DUEL_SETTLEMENT_POINTS,
    ),
    RatingFormulaItem(
        code="timely_reveal",
        label="Раскрытие результата без таймаута",
        points=TIMELY_REVEAL_POINTS,
    ),
    RatingFormulaItem(
        code="qualified_referral",
        label="Друг с подтверждённым on-chain действием",
        points=QUALIFIED_REFERRAL_POINTS,
    ),
    RatingFormulaItem(
        code="missed_reveal",
        label="Пропущенное раскрытие DUEL",
        points=MISSED_REVEAL_POINTS,
    ),
]

ACTIVE_BANK_STATES = [
    BankPositionStatus.PENDING_CONFIRMATION.value,
    BankPositionStatus.QUEUED.value,
    BankPositionStatus.PARTIALLY_FUNDED.value,
    BankPositionStatus.COMPLETED.value,
]
ACTIVE_DUEL_STATES = [
    OfferState.PENDING_FUNDING.value,
    OfferState.OPEN.value,
    OfferState.RESERVED.value,
    OfferState.MATCHED.value,
]

MONTHS_RU = (
    "",
    "ЯНВАРЬ",
    "ФЕВРАЛЬ",
    "МАРТ",
    "АПРЕЛЬ",
    "МАЙ",
    "ИЮНЬ",
    "ИЮЛЬ",
    "АВГУСТ",
    "СЕНТЯБРЬ",
    "ОКТЯБРЬ",
    "НОЯБРЬ",
    "ДЕКАБРЬ",
)


@dataclass
class RatingMetrics:
    bank_payouts: int = 0
    duel_settlements: int = 0
    timely_reveals: int = 0
    missed_reveals: int = 0
    qualified_referrals: int = 0
    terminal_duels: int = 0
    terminal_reveals: int = 0


def season_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    start = datetime(current.year, current.month, 1, tzinfo=UTC)
    end = (
        datetime(current.year + 1, 1, 1, tzinfo=UTC)
        if current.month == 12
        else datetime(current.year, current.month + 1, 1, tzinfo=UTC)
    )
    return start, end


def score_metrics(metrics: RatingMetrics) -> int:
    return max(
        0,
        metrics.bank_payouts * BANK_PAYOUT_POINTS
        + metrics.duel_settlements * DUEL_SETTLEMENT_POINTS
        + metrics.timely_reveals * TIMELY_REVEAL_POINTS
        + metrics.qualified_referrals * QUALIFIED_REFERRAL_POINTS
        + metrics.missed_reveals * MISSED_REVEAL_POINTS,
    )


def level_for_score(score: int) -> str:
    if score >= 1_000:
        return "LOOP"
    if score >= 500:
        return "ORBIT"
    if score >= 200:
        return "PULSE"
    return "SIGNAL"


async def grouped_counts(
    db: AsyncSession,
    statement: Select[Any],
) -> dict[str, int]:
    rows = (await db.execute(statement)).all()
    return {str(user_id): int(count) for user_id, count in rows if user_id is not None}


def all_user_ids(groups: Iterable[dict[str, int]]) -> set[str]:
    result: set[str] = set()
    for group in groups:
        result.update(group)
    return result


async def build_rating(
    db: AsyncSession,
    current_user: User,
    *,
    now: datetime | None = None,
) -> RatingView:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    start, end = season_window(current)

    bank_payouts = await grouped_counts(
        db,
        select(BankPosition.user_id, func.count(BankPayout.id))
        .join(BankPayout, BankPayout.position_id == BankPosition.id)
        .where(
            BankPosition.user_id.is_not(None),
            BankPayout.created_at >= start,
            BankPayout.created_at < end,
        )
        .group_by(BankPosition.user_id),
    )
    duel_settlements = await grouped_counts(
        db,
        select(DuelPlayer.user_id, func.count(func.distinct(DuelSettlement.id)))
        .join(DuelSettlement, DuelSettlement.duel_id == DuelPlayer.duel_id)
        .where(
            DuelPlayer.user_id.is_not(None),
            DuelSettlement.created_at >= start,
            DuelSettlement.created_at < end,
        )
        .group_by(DuelPlayer.user_id),
    )
    timely_reveals = await grouped_counts(
        db,
        select(DuelPlayer.user_id, func.count(DuelReveal.id))
        .join(
            DuelReveal,
            and_(
                DuelReveal.duel_id == DuelPlayer.duel_id,
                DuelReveal.offer_id == DuelPlayer.offer_id,
            ),
        )
        .join(Duel, Duel.id == DuelPlayer.duel_id)
        .where(
            DuelPlayer.user_id.is_not(None),
            DuelReveal.created_at >= start,
            DuelReveal.created_at < end,
            DuelReveal.created_at <= Duel.reveal_deadline,
        )
        .group_by(DuelPlayer.user_id),
    )
    settlement_reveals = await grouped_counts(
        db,
        select(DuelPlayer.user_id, func.count(DuelReveal.id))
        .join(
            DuelReveal,
            and_(
                DuelReveal.duel_id == DuelPlayer.duel_id,
                DuelReveal.offer_id == DuelPlayer.offer_id,
            ),
        )
        .join(DuelSettlement, DuelSettlement.duel_id == DuelPlayer.duel_id)
        .where(
            DuelPlayer.user_id.is_not(None),
            DuelSettlement.created_at >= start,
            DuelSettlement.created_at < end,
        )
        .group_by(DuelPlayer.user_id),
    )
    refunded_without_reveal = await grouped_counts(
        db,
        select(DuelPlayer.user_id, func.count(DuelPlayer.id))
        .join(Duel, Duel.id == DuelPlayer.duel_id)
        .join(DuelOffer, DuelOffer.id == DuelPlayer.offer_id)
        .outerjoin(
            DuelReveal,
            and_(
                DuelReveal.duel_id == DuelPlayer.duel_id,
                DuelReveal.offer_id == DuelPlayer.offer_id,
            ),
        )
        .where(
            DuelPlayer.user_id.is_not(None),
            DuelOffer.state == OfferState.REFUNDED.value,
            Duel.reveal_deadline >= start,
            Duel.reveal_deadline < end,
            Duel.reveal_deadline < current,
            DuelReveal.id.is_(None),
        )
        .group_by(DuelPlayer.user_id),
    )
    qualified_referrals = await grouped_counts(
        db,
        select(ReferralAttribution.inviter_user_id, func.count(ReferralAttribution.id))
        .where(
            ReferralAttribution.status == "qualified",
            ReferralAttribution.qualified_at.is_not(None),
            ReferralAttribution.qualified_at >= start,
            ReferralAttribution.qualified_at < end,
        )
        .group_by(ReferralAttribution.inviter_user_id),
    )

    circle_rows = (
        await db.execute(
            select(
                ReferralAttribution.inviter_user_id,
                ReferralAttribution.invitee_user_id,
            ).where(
                ReferralAttribution.status == "qualified",
                or_(
                    ReferralAttribution.inviter_user_id == current_user.id,
                    ReferralAttribution.invitee_user_id == current_user.id,
                ),
            )
        )
    ).all()
    circle_ids = {current_user.id}
    for inviter_id, invitee_id in circle_rows:
        circle_ids.update((str(inviter_id), str(invitee_id)))

    metric_groups = [
        bank_payouts,
        duel_settlements,
        timely_reveals,
        refunded_without_reveal,
        qualified_referrals,
    ]
    user_ids = all_user_ids(metric_groups) | circle_ids
    users = (
        await db.scalars(select(User).where(User.id.in_(user_ids)))
    ).all()

    entries: list[tuple[User, RatingMetrics, int]] = []
    for user in users:
        settled = duel_settlements.get(user.id, 0)
        revealed = timely_reveals.get(user.id, 0)
        terminal_reveals = settlement_reveals.get(user.id, 0)
        refunded_misses = refunded_without_reveal.get(user.id, 0)
        metrics = RatingMetrics(
            bank_payouts=bank_payouts.get(user.id, 0),
            duel_settlements=settled,
            timely_reveals=revealed,
            missed_reveals=max(0, settled - terminal_reveals) + refunded_misses,
            qualified_referrals=qualified_referrals.get(user.id, 0),
            terminal_duels=settled + refunded_misses,
            terminal_reveals=terminal_reveals,
        )
        entries.append((user, metrics, score_metrics(metrics)))
    entries.sort(
        key=lambda item: (
            -item[2],
            -(item[1].bank_payouts + item[1].duel_settlements),
            item[0].first_name.casefold(),
            item[0].id,
        )
    )

    ranked: list[RatingEntryView] = []
    for rank, (user, metrics, score) in enumerate(entries, start=1):
        reliability = (
            0
            if metrics.terminal_duels == 0
            else min(
                10_000,
                metrics.terminal_reveals * 10_000 // metrics.terminal_duels,
            )
        )
        ranked.append(
            RatingEntryView(
                rank=rank,
                user_id=user.id,
                first_name=user.first_name,
                username=user.username,
                photo_url=user.photo_url,
                score=score,
                level=level_for_score(score),
                bank_payouts=metrics.bank_payouts,
                duel_settlements=metrics.duel_settlements,
                timely_reveals=metrics.timely_reveals,
                missed_reveals=metrics.missed_reveals,
                qualified_referrals=metrics.qualified_referrals,
                proofs=metrics.bank_payouts + metrics.duel_settlements,
                reliability_bps=reliability,
                is_me=user.id == current_user.id,
            )
        )
    me = next(entry for entry in ranked if entry.is_me)

    active_bank_users = set(
        await db.scalars(
            select(BankPosition.user_id).where(
                BankPosition.user_id.is_not(None),
                BankPosition.current_status.in_(ACTIVE_BANK_STATES),
            )
        )
    )
    active_duel_users = set(
        await db.scalars(
            select(DuelOffer.user_id).where(
                DuelOffer.user_id.is_not(None),
                DuelOffer.state.in_(ACTIVE_DUEL_STATES),
            )
        )
    )
    since = current - timedelta(hours=24)
    bank_proofs_24h = await db.scalar(
        select(func.count()).select_from(BankPayout).where(BankPayout.created_at >= since)
    )
    duel_proofs_24h = await db.scalar(
        select(func.count())
        .select_from(DuelSettlement)
        .where(DuelSettlement.created_at >= since)
    )

    return RatingView(
        season_id=f"{start.year:04d}-{start.month:02d}",
        season_name=f"{MONTHS_RU[start.month]} · {start.year}",
        starts_at=start,
        ends_at=end,
        me=me,
        leaderboard=ranked[:50],
        circle=[entry for entry in ranked if entry.user_id in circle_ids][:20],
        pulse=RatingPulseView(
            active_participants=len(active_bank_users | active_duel_users),
            active_bank=len(active_bank_users),
            active_duels=len(active_duel_users),
            proofs_24h=int(bank_proofs_24h or 0) + int(duel_proofs_24h or 0),
        ),
        formula=RATING_FORMULA,
    )
