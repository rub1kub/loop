import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import User
from .models import (
    Team,
    TeamInvite,
    TeamJoinRequest,
    TeamMemberSeasonStats,
    TeamMembership,
    TeamRole,
    TeamScoreEvent,
    TeamSeason,
    TeamSeasonStats,
)
from .schemas import (
    TeamActivityView,
    TeamDetailView,
    TeamEntryView,
    TeamMembersPageView,
    TeamMemberView,
    TeamOverviewView,
    TeamRequestView,
    TeamSeasonView,
)

MSK = timezone(timedelta(hours=3))
TEAM_CHANGE_COOLDOWN = timedelta(hours=24)
TEAM_INVITE_TTL = timedelta(days=30)
TAG_PATTERN = re.compile(r"^[A-ZА-ЯЁ0-9]{2,8}$")
MONTHS_RU = (
    "",
    "ЯНВАРЯ",
    "ФЕВРАЛЯ",
    "МАРТА",
    "АПРЕЛЯ",
    "МАЯ",
    "ИЮНЯ",
    "ИЮЛЯ",
    "АВГУСТА",
    "СЕНТЯБРЯ",
    "ОКТЯБРЯ",
    "НОЯБРЯ",
    "ДЕКАБРЯ",
)


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def team_week_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = as_utc(now or datetime.now(UTC)).astimezone(MSK)
    monday = (current - timedelta(days=current.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday.astimezone(UTC), (monday + timedelta(days=7)).astimezone(UTC)


def season_identity(starts_at: datetime, ends_at: datetime) -> tuple[str, str]:
    local_start = as_utc(starts_at).astimezone(MSK)
    local_end = (as_utc(ends_at) - timedelta(seconds=1)).astimezone(MSK)
    iso = local_start.isocalendar()
    key = f"{iso.year}-W{iso.week:02d}"
    if local_start.month == local_end.month:
        name = f"{local_start.day}–{local_end.day} {MONTHS_RU[local_start.month]}"
    else:
        name = (
            f"{local_start.day} {MONTHS_RU[local_start.month]} — "
            f"{local_end.day} {MONTHS_RU[local_end.month]}"
        )
    return key, name


async def ensure_season(db: AsyncSession, at: datetime | None = None) -> TeamSeason:
    start, end = team_week_window(at)
    existing = cast(
        TeamSeason | None,
        await db.scalar(
            select(TeamSeason).where(TeamSeason.starts_at == start, TeamSeason.ends_at == end)
        ),
    )
    if existing is not None:
        return existing
    key, name = season_identity(start, end)
    season = TeamSeason(
        season_key=key,
        name=name,
        starts_at=start,
        ends_at=end,
        competition="bank_flow",
        formula_version=1,
        state="active",
    )
    try:
        async with db.begin_nested():
            db.add(season)
            await db.flush()
    except IntegrityError:
        existing = cast(
            TeamSeason | None,
            await db.scalar(
                select(TeamSeason).where(TeamSeason.starts_at == start, TeamSeason.ends_at == end)
            ),
        )
        if existing is None:
            raise
        return existing
    return season


def season_view(season: TeamSeason) -> TeamSeasonView:
    return TeamSeasonView(
        id=season.id,
        key=season.season_key,
        name=season.name,
        starts_at=season.starts_at,
        ends_at=season.ends_at,
        competition=season.competition,
    )


def normalize_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not 3 <= len(normalized) <= 32:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Название: от 3 до 32 знаков")
    if any(not (char.isalnum() or char in " -_.") for char in normalized):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "В названии допустимы буквы, цифры, пробел, точка, дефис и подчёркивание",
        )
    return normalized


def normalize_tag(value: str) -> str:
    tag = value.strip().upper()
    if not TAG_PATTERN.fullmatch(tag):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Тег: 2–8 букв или цифр без пробелов",
        )
    return tag


def ranked_teams_statement(season_id: str) -> Select[Any]:
    members = (
        select(
            TeamMembership.team_id.label("team_id"),
            func.count(TeamMembership.id).label("member_count"),
        )
        .where(TeamMembership.state == "active")
        .group_by(TeamMembership.team_id)
        .subquery()
    )
    flow = func.coalesce(TeamSeasonStats.flow_nano, 0)
    active = func.coalesce(TeamSeasonStats.active_members, 0)
    payouts = func.coalesce(TeamSeasonStats.bank_payouts, 0)
    base = (
        select(
            Team.id.label("id"),
            Team.slug.label("slug"),
            Team.name.label("name"),
            Team.description.label("description"),
            Team.tag.label("tag"),
            Team.mark.label("mark"),
            Team.avatar_sha256.label("avatar_sha256"),
            Team.join_policy.label("join_policy"),
            Team.created_at.label("created_at"),
            func.coalesce(members.c.member_count, 0).label("member_count"),
            active.label("active_members"),
            flow.label("flow_nano"),
            func.coalesce(TeamSeasonStats.bank_entries, 0).label("bank_entries"),
            payouts.label("bank_payouts"),
            func.coalesce(TeamSeasonStats.duel_settlements, 0).label("duel_settlements"),
        )
        .outerjoin(members, members.c.team_id == Team.id)
        .outerjoin(
            TeamSeasonStats,
            and_(
                TeamSeasonStats.team_id == Team.id,
                TeamSeasonStats.season_id == season_id,
            ),
        )
        .where(Team.state == "active")
        .subquery()
    )
    return select(
        base,
        func.row_number()
        .over(
            order_by=(
                base.c.flow_nano.desc(),
                base.c.member_count.desc(),
                base.c.active_members.desc(),
                base.c.bank_payouts.desc(),
                base.c.created_at.asc(),
                base.c.id.asc(),
            )
        )
        .label("rank"),
    )


def entry_from_row(row: Any, *, my_team_id: str | None) -> TeamEntryView:
    data = row._mapping
    return TeamEntryView(
        id=str(data["id"]),
        slug=str(data["slug"]),
        name=str(data["name"]),
        description=str(data["description"]),
        tag=str(data["tag"]),
        mark=int(data["mark"]),
        avatar_url=(
            f"/api/v1/team-cards/{data['slug']}/avatar.jpg?v={str(data['avatar_sha256'])[:12]}"
            if data["avatar_sha256"]
            else None
        ),
        join_policy=str(data["join_policy"]),
        member_count=int(data["member_count"]),
        active_members=int(data["active_members"]),
        flow_nano=int(data["flow_nano"]),
        bank_entries=int(data["bank_entries"]),
        bank_payouts=int(data["bank_payouts"]),
        duel_settlements=int(data["duel_settlements"]),
        rank=int(data["rank"]),
        is_mine=str(data["id"]) == my_team_id,
    )


async def active_membership(db: AsyncSession, user_id: str) -> TeamMembership | None:
    return cast(
        TeamMembership | None,
        await db.scalar(
            select(TeamMembership).where(
                TeamMembership.user_id == user_id,
                TeamMembership.state == "active",
            )
        ),
    )


async def membership_at(db: AsyncSession, user_id: str, at: datetime) -> TeamMembership | None:
    moment = as_utc(at)
    return cast(
        TeamMembership | None,
        await db.scalar(
            select(TeamMembership)
            .where(
                TeamMembership.user_id == user_id,
                TeamMembership.joined_at <= moment,
                or_(TeamMembership.left_at.is_(None), TeamMembership.left_at > moment),
            )
            .order_by(TeamMembership.joined_at.desc())
            .limit(1)
        ),
    )


async def my_team_id(db: AsyncSession, user_id: str) -> str | None:
    membership = await active_membership(db, user_id)
    return membership.team_id if membership else None


async def leaderboard_entries(
    db: AsyncSession,
    season: TeamSeason,
    user_id: str,
    *,
    limit: int = 30,
    offset: int = 0,
    query: str | None = None,
) -> tuple[list[TeamEntryView], int]:
    mine = await my_team_id(db, user_id)
    ranked = ranked_teams_statement(season.id).subquery()
    statement = select(ranked)
    count_statement = select(func.count()).select_from(ranked)
    if query:
        needle = f"%{query.strip().lower()}%"
        filter_clause = func.lower(ranked.c.name).like(needle)
        statement = statement.where(filter_clause)
        count_statement = count_statement.where(filter_clause)
    rows = (await db.execute(statement.order_by(ranked.c.rank).offset(offset).limit(limit))).all()
    total = int(await db.scalar(count_statement) or 0)
    return [entry_from_row(row, my_team_id=mine) for row in rows], total


async def ranked_team_entry(
    db: AsyncSession,
    season: TeamSeason,
    *,
    user_id: str | None,
    team_id: str | None = None,
    slug: str | None = None,
) -> TeamEntryView | None:
    mine = await my_team_id(db, user_id) if user_id else None
    ranked = ranked_teams_statement(season.id).subquery()
    statement = select(ranked)
    if team_id is not None:
        statement = statement.where(ranked.c.id == team_id)
    elif slug is not None:
        statement = statement.where(ranked.c.slug == slug)
    else:
        return None
    row = (await db.execute(statement)).first()
    return entry_from_row(row, my_team_id=mine) if row else None


async def team_detail(
    db: AsyncSession,
    team: Team,
    user: User,
    season: TeamSeason,
) -> TeamDetailView:
    entry = await ranked_team_entry(db, season, user_id=user.id, team_id=team.id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Команда не найдена")
    membership = await active_membership(db, user.id)
    my_role = membership.role if membership and membership.team_id == team.id else None
    pending_request = None
    if my_role is None:
        pending_request = await db.scalar(
            select(TeamJoinRequest.id).where(
                TeamJoinRequest.team_id == team.id,
                TeamJoinRequest.user_id == user.id,
                TeamJoinRequest.state == "pending",
            )
        )

    member_rows = (
        await db.execute(
            select(TeamMembership, User, TeamMemberSeasonStats)
            .join(User, User.id == TeamMembership.user_id)
            .outerjoin(
                TeamMemberSeasonStats,
                and_(
                    TeamMemberSeasonStats.season_id == season.id,
                    TeamMemberSeasonStats.team_id == team.id,
                    TeamMemberSeasonStats.user_id == TeamMembership.user_id,
                ),
            )
            .where(TeamMembership.team_id == team.id, TeamMembership.state == "active")
            .order_by(
                func.coalesce(TeamMemberSeasonStats.flow_nano, 0).desc(),
                TeamMembership.joined_at,
            )
            .limit(20)
        )
    ).all()
    members = [
        TeamMemberView(
            user_id=member_user.id,
            first_name=member_user.first_name,
            username=member_user.username,
            photo_url=member_user.photo_url,
            role=member.role,
            joined_at=member.joined_at,
            flow_nano=stats.flow_nano if stats else 0,
            bank_entries=stats.bank_entries if stats else 0,
            bank_payouts=stats.bank_payouts if stats else 0,
            duel_settlements=stats.duel_settlements if stats else 0,
            is_me=member_user.id == user.id,
        )
        for member, member_user, stats in member_rows
    ]
    activity_rows = (
        await db.execute(
            select(TeamScoreEvent, User)
            .join(User, User.id == TeamScoreEvent.user_id)
            .where(
                TeamScoreEvent.team_id == team.id,
                TeamScoreEvent.season_id == season.id,
            )
            .order_by(TeamScoreEvent.event_at.desc(), TeamScoreEvent.id.desc())
            .limit(20)
        )
    ).all()
    activity = [
        TeamActivityView(
            id=event.id,
            kind=event.source_kind,
            user_id=event_user.id,
            first_name=event_user.first_name,
            username=event_user.username,
            amount_nano=event.amount_nano,
            tx_hash=event.tx_hash,
            event_at=event.event_at,
        )
        for event, event_user in activity_rows
    ]
    requests: list[TeamRequestView] = []
    if my_role in {TeamRole.OWNER.value, TeamRole.ADMIN.value}:
        request_rows = (
            await db.execute(
                select(TeamJoinRequest, User)
                .join(User, User.id == TeamJoinRequest.user_id)
                .where(TeamJoinRequest.team_id == team.id, TeamJoinRequest.state == "pending")
                .order_by(TeamJoinRequest.created_at)
                .limit(50)
            )
        ).all()
        requests = [
            TeamRequestView(
                id=request.id,
                user_id=request_user.id,
                first_name=request_user.first_name,
                username=request_user.username,
                photo_url=request_user.photo_url,
                created_at=request.created_at,
            )
            for request, request_user in request_rows
        ]
    my_stats = await db.scalar(
        select(TeamMemberSeasonStats).where(
            TeamMemberSeasonStats.season_id == season.id,
            TeamMemberSeasonStats.team_id == team.id,
            TeamMemberSeasonStats.user_id == user.id,
        )
    )
    return TeamDetailView(
        **entry.model_dump(),
        my_role=my_role,
        my_join_state="joined" if my_role else "pending" if pending_request else "none",
        my_flow_nano=my_stats.flow_nano if my_stats else 0,
        top_members=members,
        recent_activity=activity,
        pending_requests=requests,
    )


async def team_members_page(
    db: AsyncSession,
    team: Team,
    user: User,
    season: TeamSeason,
    *,
    offset: int,
    limit: int,
) -> TeamMembersPageView:
    total = int(
        await db.scalar(
            select(func.count())
            .select_from(TeamMembership)
            .where(TeamMembership.team_id == team.id, TeamMembership.state == "active")
        )
        or 0
    )
    rows = (
        await db.execute(
            select(TeamMembership, User, TeamMemberSeasonStats)
            .join(User, User.id == TeamMembership.user_id)
            .outerjoin(
                TeamMemberSeasonStats,
                and_(
                    TeamMemberSeasonStats.season_id == season.id,
                    TeamMemberSeasonStats.team_id == team.id,
                    TeamMemberSeasonStats.user_id == TeamMembership.user_id,
                ),
            )
            .where(TeamMembership.team_id == team.id, TeamMembership.state == "active")
            .order_by(
                func.coalesce(TeamMemberSeasonStats.flow_nano, 0).desc(),
                TeamMembership.joined_at,
            )
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = [
        TeamMemberView(
            user_id=member_user.id,
            first_name=member_user.first_name,
            username=member_user.username,
            photo_url=member_user.photo_url,
            role=member.role,
            joined_at=member.joined_at,
            flow_nano=stats.flow_nano if stats else 0,
            bank_entries=stats.bank_entries if stats else 0,
            bank_payouts=stats.bank_payouts if stats else 0,
            duel_settlements=stats.duel_settlements if stats else 0,
            is_me=member_user.id == user.id,
        )
        for member, member_user, stats in rows
    ]
    return TeamMembersPageView(items=items, total=total, offset=offset, limit=limit)


async def overview(db: AsyncSession, user: User, now: datetime | None = None) -> TeamOverviewView:
    season = await ensure_season(db, now)
    leaderboard, _ = await leaderboard_entries(db, season, user.id, limit=30)
    membership = await active_membership(db, user.id)
    detail = None
    if membership:
        team = await db.get(Team, membership.team_id)
        if team is not None:
            detail = await team_detail(db, team, user, season)
    return TeamOverviewView(
        season=season_view(season),
        my_team=detail,
        leaderboard=leaderboard,
    )


async def create_team(
    db: AsyncSession,
    user: User,
    *,
    name: str,
    tag: str | None,
    join_policy: str,
) -> Team:
    now = datetime.now(UTC)
    await db.scalar(select(User).where(User.id == user.id).with_for_update())
    if await active_membership(db, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Сначала покиньте текущую команду")
    await assert_change_cooldown(db, user.id, now)
    normalized_name = normalize_name(name)
    if tag is not None:
        normalized_tag = normalize_tag(tag)
        if await db.scalar(select(Team.id).where(Team.tag == normalized_tag)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Такой тег уже занят")
    else:
        # `tag` remains an internal unique key for backward compatibility. It
        # is generated here so people only have to name their team once.
        for _ in range(8):
            normalized_tag = secrets.token_hex(4).upper()
            if not await db.scalar(select(Team.id).where(Team.tag == normalized_tag)):
                break
        else:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Не удалось создать команду")
    slug = secrets.token_urlsafe(8).rstrip("=")
    mark = int(hashlib.sha256(normalized_tag.encode()).hexdigest()[:8], 16) % 12
    team = Team(
        slug=slug,
        name=normalized_name,
        tag=normalized_tag,
        mark=mark,
        join_policy=join_policy,
        owner_user_id=user.id,
    )
    db.add(team)
    await db.flush()
    db.add(
        TeamMembership(
            team_id=team.id,
            user_id=user.id,
            role=TeamRole.OWNER.value,
            state="active",
        )
    )
    await db.flush()
    return team


async def assert_manager(
    db: AsyncSession,
    team: Team,
    user_id: str,
    *,
    owner_only: bool = False,
) -> TeamMembership:
    membership = await active_membership(db, user_id)
    allowed = {TeamRole.OWNER.value} if owner_only else {TeamRole.OWNER.value, TeamRole.ADMIN.value}
    if membership is None or membership.team_id != team.id or membership.role not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
    return membership


async def assert_change_cooldown(db: AsyncSession, user_id: str, now: datetime) -> None:
    previous = await db.scalar(
        select(TeamMembership)
        .where(
            TeamMembership.user_id == user_id,
            TeamMembership.state.in_(["left", "kicked"]),
            TeamMembership.left_at.is_not(None),
        )
        .order_by(TeamMembership.left_at.desc())
        .limit(1)
    )
    if previous and previous.left_at and as_utc(previous.left_at) > now - TEAM_CHANGE_COOLDOWN:
        available = as_utc(previous.left_at) + TEAM_CHANGE_COOLDOWN
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Новую команду можно выбрать после {available.isoformat()}",
        )


def invite_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def resolve_invite(db: AsyncSession, token: str, now: datetime | None = None) -> TeamInvite:
    current = now or datetime.now(UTC)
    invite = await db.scalar(
        select(TeamInvite).where(TeamInvite.token_hash == invite_digest(token))
    )
    if invite is None or invite.revoked_at is not None or as_utc(invite.expires_at) <= current:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Приглашение больше не действует")
    return invite


async def create_invite(db: AsyncSession, team: Team, user: User) -> tuple[TeamInvite, str]:
    membership = await active_membership(db, user.id)
    if membership is None or membership.team_id != team.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Приглашать может участник команды")
    token = secrets.token_urlsafe(12).rstrip("=")
    invite = TeamInvite(
        team_id=team.id,
        inviter_user_id=user.id,
        token_hash=invite_digest(token),
        expires_at=datetime.now(UTC) + TEAM_INVITE_TTL,
    )
    db.add(invite)
    await db.flush()
    return invite, token


async def join_team(
    db: AsyncSession,
    team: Team,
    user: User,
    *,
    invite_token: str | None = None,
) -> str:
    now = datetime.now(UTC)
    await db.scalar(select(User).where(User.id == user.id).with_for_update())
    membership = await active_membership(db, user.id)
    if membership:
        if membership.team_id == team.id:
            return "joined"
        raise HTTPException(status.HTTP_409_CONFLICT, "Вы уже состоите в другой команде")
    await assert_change_cooldown(db, user.id, now)
    valid_invite = False
    if invite_token:
        invite = await resolve_invite(db, invite_token, now)
        valid_invite = invite.team_id == team.id
        if not valid_invite:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Приглашение от другой команды")
    if team.join_policy == "invite" and not valid_invite:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "В эту команду входят по приглашению")
    if team.join_policy == "request" and not valid_invite:
        existing = await db.scalar(
            select(TeamJoinRequest).where(
                TeamJoinRequest.user_id == user.id,
                TeamJoinRequest.state == "pending",
            )
        )
        if existing:
            if existing.team_id == team.id:
                return "requested"
            raise HTTPException(status.HTTP_409_CONFLICT, "У вас уже есть другая заявка")
        db.add(TeamJoinRequest(team_id=team.id, user_id=user.id, state="pending"))
        await db.flush()
        return "requested"
    db.add(TeamMembership(team_id=team.id, user_id=user.id, role="member", state="active"))
    await db.execute(
        update(TeamJoinRequest)
        .where(TeamJoinRequest.user_id == user.id, TeamJoinRequest.state == "pending")
        .values(state="cancelled", decided_at=now)
    )
    await db.flush()
    return "joined"


async def leave_team(db: AsyncSession, team: Team, user: User) -> None:
    membership = await active_membership(db, user.id)
    if membership is None or membership.team_id != team.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Вы не состоите в этой команде")
    if membership.role == TeamRole.OWNER.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Сначала передайте управление другому участнику",
        )
    membership.state = "left"
    membership.left_at = datetime.now(UTC)


async def decide_request(
    db: AsyncSession,
    team: Team,
    manager: User,
    request_id: str,
    *,
    approve: bool,
) -> None:
    await assert_manager(db, team, manager.id)
    request = await db.scalar(
        select(TeamJoinRequest)
        .where(
            TeamJoinRequest.id == request_id,
            TeamJoinRequest.team_id == team.id,
            TeamJoinRequest.state == "pending",
        )
        .with_for_update()
    )
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка уже обработана")
    now = datetime.now(UTC)
    request.decided_by_user_id = manager.id
    request.decided_at = now
    if not approve:
        request.state = "rejected"
        return
    await db.scalar(select(User).where(User.id == request.user_id).with_for_update())
    if await active_membership(db, request.user_id):
        request.state = "cancelled"
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь уже выбрал другую команду")
    await assert_change_cooldown(db, request.user_id, now)
    db.add(
        TeamMembership(
            team_id=team.id,
            user_id=request.user_id,
            role=TeamRole.MEMBER.value,
            state="active",
        )
    )
    request.state = "approved"
    await db.flush()


async def change_member_role(
    db: AsyncSession,
    team: Team,
    owner: User,
    member_user_id: str,
    role: str,
) -> None:
    await assert_manager(db, team, owner.id, owner_only=True)
    membership = await db.scalar(
        select(TeamMembership).where(
            TeamMembership.team_id == team.id,
            TeamMembership.user_id == member_user_id,
            TeamMembership.state == "active",
        )
    )
    if membership is None or membership.role == TeamRole.OWNER.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Участник не найден")
    membership.role = role


async def transfer_team(
    db: AsyncSession,
    team: Team,
    owner: User,
    member_user_id: str,
) -> None:
    current_owner = await assert_manager(db, team, owner.id, owner_only=True)
    target = await db.scalar(
        select(TeamMembership).where(
            TeamMembership.team_id == team.id,
            TeamMembership.user_id == member_user_id,
            TeamMembership.state == "active",
        )
    )
    if target is None or target.id == current_owner.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Участник не найден")
    current_owner.role = TeamRole.ADMIN.value
    # The partial unique index guarantees one active owner. Flush the demotion
    # first so SQLite and PostgreSQL never observe two owner rows while the
    # transaction itself remains atomic until the router commits it.
    await db.flush([current_owner])
    target.role = TeamRole.OWNER.value
    team.owner_user_id = member_user_id
    await db.flush([target, team])


async def kick_member(
    db: AsyncSession,
    team: Team,
    manager: User,
    member_user_id: str,
) -> None:
    actor = await assert_manager(db, team, manager.id)
    target = await db.scalar(
        select(TeamMembership).where(
            TeamMembership.team_id == team.id,
            TeamMembership.user_id == member_user_id,
            TeamMembership.state == "active",
        )
    )
    if target is None or target.role == TeamRole.OWNER.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Участник не найден")
    if actor.role == TeamRole.ADMIN.value and target.role != TeamRole.MEMBER.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Управляющий не может удалить управляющего")
    target.state = "kicked"
    target.left_at = datetime.now(UTC)
