from datetime import UTC, datetime

import structlog
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..bank.models import BankPayout, BankPosition
from ..duel.models import Duel, DuelOffer, DuelPlayer, DuelSettlement
from .models import (
    TeamMemberSeasonStats,
    TeamScoreEvent,
    TeamSeasonStats,
)
from .service import as_utc, ensure_season, membership_at, team_week_window

logger = structlog.get_logger()


async def record_team_score_event(
    db: AsyncSession,
    *,
    user_id: str | None,
    source_kind: str,
    source_entity_id: str,
    source_key: str,
    amount_nano: int,
    network: int,
    tx_hash: str,
    event_at: datetime,
) -> bool:
    """Attach a finalized projection event to membership at chain time.

    Membership is temporal and the ledger is immutable. A person changing
    teams after broadcasting a transaction therefore cannot move its result,
    and replaying the same block cannot count it twice.
    """
    if user_id is None:
        return False
    moment = as_utc(event_at)
    membership = await membership_at(db, user_id, moment)
    if membership is None:
        return False
    if await db.scalar(select(TeamScoreEvent.id).where(TeamScoreEvent.source_key == source_key)):
        return False
    season = await ensure_season(db, moment)
    event = TeamScoreEvent(
        season_id=season.id,
        team_id=membership.team_id,
        membership_id=membership.id,
        user_id=user_id,
        source_kind=source_kind,
        source_entity_id=source_entity_id,
        source_key=source_key,
        amount_nano=max(0, amount_nano),
        network=network,
        tx_hash=tx_hash,
        event_at=moment,
    )
    try:
        async with db.begin_nested():
            db.add(event)
            await db.flush()
    except IntegrityError:
        return False

    member_stats = await db.scalar(
        select(TeamMemberSeasonStats)
        .where(
            TeamMemberSeasonStats.season_id == season.id,
            TeamMemberSeasonStats.team_id == membership.team_id,
            TeamMemberSeasonStats.user_id == user_id,
        )
        .with_for_update()
    )
    first_member_event = member_stats is None
    if member_stats is None:
        member_stats = TeamMemberSeasonStats(
            season_id=season.id,
            team_id=membership.team_id,
            user_id=user_id,
            flow_nano=0,
            bank_entries=0,
            bank_payouts=0,
            duel_settlements=0,
        )
        db.add(member_stats)

    team_stats = await db.scalar(
        select(TeamSeasonStats)
        .where(
            TeamSeasonStats.season_id == season.id,
            TeamSeasonStats.team_id == membership.team_id,
        )
        .with_for_update()
    )
    if team_stats is None:
        team_stats = TeamSeasonStats(
            season_id=season.id,
            team_id=membership.team_id,
            flow_nano=0,
            bank_entries=0,
            bank_payouts=0,
            duel_settlements=0,
            active_members=0,
        )
        db.add(team_stats)

    if source_kind == "bank_entry":
        member_stats.flow_nano += max(0, amount_nano)
        member_stats.bank_entries += 1
        team_stats.flow_nano += max(0, amount_nano)
        team_stats.bank_entries += 1
    elif source_kind == "bank_payout":
        member_stats.bank_payouts += 1
        team_stats.bank_payouts += 1
    elif source_kind == "duel_settlement":
        member_stats.duel_settlements += 1
        team_stats.duel_settlements += 1
    else:
        raise ValueError(f"unsupported team score source: {source_kind}")
    if first_member_event:
        team_stats.active_members += 1
    member_stats.last_event_at = moment
    if team_stats.last_event_at is None or as_utc(team_stats.last_event_at) < moment:
        team_stats.last_event_at = moment
    await db.flush()
    return True


async def reconcile_team_score_events(
    db: AsyncSession,
    *,
    network: int,
    bank_contract_address: str,
    duel_contract_address: str,
    limit: int = 250,
) -> int:
    """Repair social events without ever blocking the financial projection."""
    start, end = team_week_window(datetime.now(UTC))
    added = 0
    bank_entries = (
        await db.execute(
            select(BankPosition)
            .outerjoin(
                TeamScoreEvent,
                and_(
                    TeamScoreEvent.source_kind == "bank_entry",
                    TeamScoreEvent.source_entity_id == BankPosition.id,
                    TeamScoreEvent.user_id == BankPosition.user_id,
                ),
            )
            .where(
                BankPosition.network == network,
                BankPosition.contract_address == bank_contract_address,
                BankPosition.user_id.is_not(None),
                BankPosition.confirmed_at.is_not(None),
                BankPosition.confirmed_at >= start,
                BankPosition.confirmed_at < end,
                BankPosition.funding_transaction.is_not(None),
                TeamScoreEvent.id.is_(None),
            )
            .order_by(BankPosition.confirmed_at)
            .limit(limit)
        )
    ).scalars()
    for position in bank_entries:
        added += int(
            await record_team_score_event(
                db,
                user_id=position.user_id,
                source_kind="bank_entry",
                source_entity_id=position.id,
                source_key=f"bank_entry:{position.network}:{position.id}",
                amount_nano=position.principal_nano,
                network=position.network,
                tx_hash=position.funding_transaction or "",
                event_at=position.confirmed_at or start,
            )
        )
    remaining = max(0, limit - added)
    if remaining:
        payout_rows = (
            await db.execute(
                select(BankPayout, BankPosition)
                .join(BankPosition, BankPosition.id == BankPayout.position_id)
                .outerjoin(
                    TeamScoreEvent,
                    and_(
                        TeamScoreEvent.source_kind == "bank_payout",
                        TeamScoreEvent.source_entity_id == BankPayout.id,
                        TeamScoreEvent.user_id == BankPosition.user_id,
                    ),
                )
                .where(
                    BankPosition.network == network,
                    BankPosition.contract_address == bank_contract_address,
                    BankPosition.user_id.is_not(None),
                    BankPayout.created_at >= start,
                    BankPayout.created_at < end,
                    TeamScoreEvent.id.is_(None),
                )
                .order_by(BankPayout.created_at)
                .limit(remaining)
            )
        ).all()
        for payout, position in payout_rows:
            added += int(
                await record_team_score_event(
                    db,
                    user_id=position.user_id,
                    source_kind="bank_payout",
                    source_entity_id=payout.id,
                    source_key=f"bank_payout:{payout.network}:{payout.id}",
                    amount_nano=0,
                    network=payout.network,
                    tx_hash=payout.tx_hash,
                    event_at=payout.created_at,
                )
            )
    remaining = max(0, limit - added)
    if remaining:
        duel_rows = (
            await db.execute(
                select(DuelSettlement, Duel, DuelPlayer)
                .join(Duel, Duel.id == DuelSettlement.duel_id)
                .join(DuelPlayer, DuelPlayer.duel_id == Duel.id)
                .join(DuelOffer, DuelOffer.id == DuelPlayer.offer_id)
                .outerjoin(
                    TeamScoreEvent,
                    and_(
                        TeamScoreEvent.source_kind == "duel_settlement",
                        TeamScoreEvent.source_entity_id == DuelSettlement.id,
                        TeamScoreEvent.user_id == DuelPlayer.user_id,
                    ),
                )
                .where(
                    Duel.network == network,
                    DuelOffer.contract_address == duel_contract_address,
                    DuelPlayer.user_id.is_not(None),
                    DuelSettlement.created_at >= start,
                    DuelSettlement.created_at < end,
                    TeamScoreEvent.id.is_(None),
                )
                .order_by(DuelSettlement.created_at)
                .limit(remaining)
            )
        ).all()
        for settlement, duel, player in duel_rows:
            del duel
            added += int(
                await record_team_score_event(
                    db,
                    user_id=player.user_id,
                    source_kind="duel_settlement",
                    source_entity_id=settlement.id,
                    source_key=f"duel_settlement:{network}:{settlement.id}:{player.user_id}",
                    amount_nano=0,
                    network=network,
                    tx_hash=settlement.tx_hash,
                    event_at=settlement.created_at,
                )
            )
    return added


async def reconcile_team_score_events_safely(
    db: AsyncSession,
    *,
    network: int,
    bank_contract_address: str,
    duel_contract_address: str,
) -> int:
    try:
        async with db.begin_nested():
            return await reconcile_team_score_events(
                db,
                network=network,
                bank_contract_address=bank_contract_address,
                duel_contract_address=duel_contract_address,
            )
    except Exception as exc:
        logger.warning(
            "team_score_reconciliation_failed",
            error=type(exc).__name__,
            detail=str(exc),
        )
        return 0
