import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO

from aiogram.exceptions import TelegramAPIError
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ...dependencies import Config, CurrentUser, Db, require_full_access
from ...models import User
from ...referrals import get_or_create_referral_code
from ...schemas import PreparedResultShareView
from .card import build_team_invite_inline, render_team_card
from .models import Team, TeamMembership
from .schemas import (
    TeamCreateRequest,
    TeamDetailView,
    TeamInvitePreviewView,
    TeamJoinRequestBody,
    TeamJoinResultView,
    TeamMembersPageView,
    TeamOverviewView,
    TeamRequestDecision,
    TeamRoleUpdateRequest,
    TeamSearchView,
    TeamTransferRequest,
    TeamUpdateRequest,
)
from .service import (
    active_membership,
    assert_manager,
    change_member_role,
    create_invite,
    create_team,
    decide_request,
    ensure_season,
    join_team,
    kick_member,
    leaderboard_entries,
    leave_team,
    normalize_name,
    overview,
    ranked_team_entry,
    resolve_invite,
    team_detail,
    team_members_page,
    transfer_team,
)

router = APIRouter(
    prefix="/teams",
    tags=["TEAMS"],
    dependencies=[Depends(require_full_access)],
)
public_router = APIRouter(prefix="/team-cards", tags=["TEAMS"])

TEAM_AVATAR_MAX_BYTES = 5 * 1024 * 1024
TEAM_AVATAR_MAX_PIXELS = 36_000_000
TEAM_AVATAR_SIDE = 512
TEAM_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp"}


async def read_team_avatar(request: Request) -> bytes:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in TEAM_AVATAR_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Поддерживаются JPG, PNG и WebP",
        )
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > TEAM_AVATAR_MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл больше 5 МБ")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > TEAM_AVATAR_MAX_BYTES:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл больше 5 МБ")
        chunks.append(chunk)
    if not size:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Изображение пустое")
    return b"".join(chunks)


def normalize_team_avatar(source: bytes) -> bytes:
    try:
        with Image.open(BytesIO(source)) as probe:
            width, height = probe.size
            if width < 64 or height < 64:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "Изображение должно быть не меньше 64×64",
                )
            if width * height > TEAM_AVATAR_MAX_PIXELS:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "Изображение слишком большое",
                )
            probe.verify()
        with Image.open(BytesIO(source)) as opened:
            image = ImageOps.exif_transpose(opened)
            square = ImageOps.fit(
                image,
                (TEAM_AVATAR_SIDE, TEAM_AVATAR_SIDE),
                method=Image.Resampling.LANCZOS,
            ).convert("RGBA")
            normalized = Image.new("RGB", square.size, "black")
            normalized.paste(square, mask=square.getchannel("A"))
            normalized = ImageOps.grayscale(normalized).convert("RGB")
            output = BytesIO()
            normalized.save(output, format="JPEG", quality=88, optimize=True, progressive=True)
            return output.getvalue()
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Не удалось прочитать изображение",
        ) from exc


async def get_active_team(db: Db, slug: str) -> Team:
    team = await db.scalar(select(Team).where(Team.slug == slug, Team.state == "active"))
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Команда не найдена")
    return team


@router.get("/overview", response_model=TeamOverviewView)
async def teams_overview(user: CurrentUser, db: Db) -> TeamOverviewView:
    result = await overview(db, user)
    await db.commit()
    return result


@router.get("/search", response_model=TeamSearchView)
async def search_teams(
    user: CurrentUser,
    db: Db,
    q: str = Query(default="", max_length=32),
    offset: int = Query(default=0, ge=0, le=100_000),
    limit: int = Query(default=20, ge=1, le=50),
) -> TeamSearchView:
    season = await ensure_season(db)
    items, total = await leaderboard_entries(
        db,
        season,
        user.id,
        limit=limit,
        offset=offset,
        query=q or None,
    )
    await db.commit()
    return TeamSearchView(items=items, total=total, offset=offset, limit=limit)


@router.get("/invites/{token}", response_model=TeamInvitePreviewView)
async def team_invite_preview(token: str, user: CurrentUser, db: Db) -> TeamInvitePreviewView:
    invite = await resolve_invite(db, token)
    team = await db.get(Team, invite.team_id)
    inviter = await db.get(User, invite.inviter_user_id)
    if team is None or team.state != "active" or inviter is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Приглашение больше не действует")
    season = await ensure_season(db)
    entry = await ranked_team_entry(db, season, user_id=user.id, team_id=team.id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Команда не найдена")
    await db.commit()
    return TeamInvitePreviewView(
        token=token,
        expires_at=invite.expires_at,
        team=entry,
        inviter_name=inviter.first_name,
    )


@router.post("/invites/{token}/join", response_model=TeamJoinResultView)
async def join_from_invite(token: str, user: CurrentUser, db: Db) -> TeamJoinResultView:
    invite = await resolve_invite(db, token)
    team = await db.get(Team, invite.team_id)
    if team is None or team.state != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Команда не найдена")
    state = await join_team(db, team, user, invite_token=token)
    await db.commit()
    season = await ensure_season(db)
    detail = await team_detail(db, team, user, season)
    await db.commit()
    return TeamJoinResultView(state=state, team=detail)


@router.post("", response_model=TeamDetailView, status_code=status.HTTP_201_CREATED)
async def new_team(body: TeamCreateRequest, user: CurrentUser, db: Db) -> TeamDetailView:
    try:
        team = await create_team(
            db,
            user,
            name=body.name,
            tag=body.tag,
            join_policy=body.join_policy,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Название или тег уже заняты") from exc
    season = await ensure_season(db)
    detail = await team_detail(db, team, user, season)
    await db.commit()
    return detail


@router.get("/{slug}", response_model=TeamDetailView)
async def get_team(slug: str, user: CurrentUser, db: Db) -> TeamDetailView:
    team = await get_active_team(db, slug)
    season = await ensure_season(db)
    detail = await team_detail(db, team, user, season)
    await db.commit()
    return detail


@router.get("/{slug}/members", response_model=TeamMembersPageView)
async def get_team_members(
    slug: str,
    user: CurrentUser,
    db: Db,
    offset: int = Query(default=0, ge=0, le=1_000_000),
    limit: int = Query(default=50, ge=1, le=100),
) -> TeamMembersPageView:
    team = await get_active_team(db, slug)
    season = await ensure_season(db)
    page = await team_members_page(db, team, user, season, offset=offset, limit=limit)
    await db.commit()
    return page


@router.patch("/{slug}", response_model=TeamDetailView)
async def update_team(
    slug: str,
    body: TeamUpdateRequest,
    user: CurrentUser,
    db: Db,
) -> TeamDetailView:
    team = await get_active_team(db, slug)
    changes_brand = body.name is not None or body.description is not None or body.mark is not None
    await assert_manager(db, team, user.id, owner_only=changes_brand)
    if body.name is not None:
        team.name = normalize_name(body.name)
    if body.description is not None:
        team.description = body.description
    if body.mark is not None:
        team.mark = body.mark
    if body.join_policy is not None:
        team.join_policy = body.join_policy
    await db.commit()
    season = await ensure_season(db)
    detail = await team_detail(db, team, user, season)
    await db.commit()
    return detail


@router.put("/{slug}/avatar", response_model=TeamDetailView)
async def upload_team_avatar(
    slug: str,
    request: Request,
    user: CurrentUser,
    db: Db,
) -> TeamDetailView:
    team = await get_active_team(db, slug)
    await assert_manager(db, team, user.id, owner_only=True)
    image = normalize_team_avatar(await read_team_avatar(request))
    team.avatar_jpeg = image
    team.avatar_sha256 = hashlib.sha256(image).hexdigest()
    await db.commit()
    season = await ensure_season(db)
    detail = await team_detail(db, team, user, season)
    await db.commit()
    return detail


@router.delete("/{slug}/avatar", response_model=TeamDetailView)
async def delete_team_avatar(slug: str, user: CurrentUser, db: Db) -> TeamDetailView:
    team = await get_active_team(db, slug)
    await assert_manager(db, team, user.id, owner_only=True)
    team.avatar_jpeg = None
    team.avatar_sha256 = None
    await db.commit()
    season = await ensure_season(db)
    detail = await team_detail(db, team, user, season)
    await db.commit()
    return detail


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_team(slug: str, user: CurrentUser, db: Db) -> Response:
    team = await get_active_team(db, slug)
    await assert_manager(db, team, user.id, owner_only=True)
    now = datetime.now(UTC)
    team.state = "archived"
    await db.execute(
        update(TeamMembership)
        .where(TeamMembership.team_id == team.id, TeamMembership.state == "active")
        .values(state="left", left_at=now)
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{slug}/join", response_model=TeamJoinResultView)
async def join_by_slug(
    slug: str,
    body: TeamJoinRequestBody,
    user: CurrentUser,
    db: Db,
) -> TeamJoinResultView:
    team = await get_active_team(db, slug)
    state = await join_team(db, team, user, invite_token=body.invite_token)
    await db.commit()
    season = await ensure_season(db)
    detail = await team_detail(db, team, user, season)
    await db.commit()
    return TeamJoinResultView(state=state, team=detail)


@router.post("/{slug}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave(slug: str, user: CurrentUser, db: Db) -> Response:
    team = await get_active_team(db, slug)
    await leave_team(db, team, user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{slug}/share", response_model=PreparedResultShareView)
async def prepare_team_share(
    slug: str,
    user: CurrentUser,
    db: Db,
    settings: Config,
    request: Request,
) -> PreparedResultShareView:
    team = await get_active_team(db, slug)
    membership = await active_membership(db, user.id)
    if membership is None or membership.team_id != team.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Приглашать может участник команды")
    bot = request.app.state.bot
    if bot is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram сейчас недоступен")
    invite, token = await create_invite(db, team, user)
    referral = await get_or_create_referral_code(db, user.id)
    season = await ensure_season(db)
    entry = await ranked_team_entry(db, season, user_id=user.id, team_id=team.id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Команда не найдена")
    try:
        prepared = await bot.save_prepared_inline_message(
            user_id=user.telegram_id,
            result=build_team_invite_inline(
                settings=settings,
                team=entry,
                token=token,
                referral_code=referral.code,
                inviter_name=user.first_name,
            ),
            allow_user_chats=True,
            allow_bot_chats=False,
            allow_group_chats=True,
            allow_channel_chats=True,
        )
    except TelegramAPIError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram сейчас недоступен"
        ) from exc
    expiration = prepared.expiration_date
    if isinstance(expiration, int):
        expiration = datetime.fromtimestamp(expiration, UTC)
    elif isinstance(expiration, timedelta):
        expiration = datetime.now(UTC) + expiration
    elif expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=UTC)
    await db.commit()
    return PreparedResultShareView(
        prepared_message_id=prepared.id,
        expiration_date=expiration,
        fallback_query=f"team {token}",
    )


@router.post("/{slug}/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def process_join_request(
    slug: str,
    request_id: str,
    body: TeamRequestDecision,
    user: CurrentUser,
    db: Db,
) -> Response:
    team = await get_active_team(db, slug)
    await decide_request(db, team, user, request_id, approve=body.approve)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{slug}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_member_role(
    slug: str,
    member_user_id: str,
    body: TeamRoleUpdateRequest,
    user: CurrentUser,
    db: Db,
) -> Response:
    team = await get_active_team(db, slug)
    await change_member_role(db, team, user, member_user_id, body.role)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{slug}/members/{member_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    slug: str,
    member_user_id: str,
    user: CurrentUser,
    db: Db,
) -> Response:
    team = await get_active_team(db, slug)
    await kick_member(db, team, user, member_user_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{slug}/transfer", status_code=status.HTTP_204_NO_CONTENT)
async def transfer_ownership(
    slug: str,
    body: TeamTransferRequest,
    user: CurrentUser,
    db: Db,
) -> Response:
    team = await get_active_team(db, slug)
    await transfer_team(db, team, user, body.user_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.get("/{slug}.jpg", response_class=Response, include_in_schema=False)
async def team_card(slug: str, db: Db) -> Response:
    team = await db.scalar(select(Team).where(Team.slug == slug, Team.state == "active"))
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Команда не найдена")
    season = await ensure_season(db)
    entry = await ranked_team_entry(db, season, user_id=None, team_id=team.id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Команда не найдена")
    image = render_team_card(
        entry.name,
        entry.tag,
        entry.mark,
        entry.rank,
        entry.flow_nano,
        entry.member_count,
    )
    await db.commit()
    return Response(
        image,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=300, stale-while-revalidate=3600"},
    )


@public_router.get("/{slug}/avatar.jpg", response_class=Response, include_in_schema=False)
async def team_avatar(slug: str, request: Request, db: Db) -> Response:
    row = (
        await db.execute(
            select(Team.avatar_jpeg, Team.avatar_sha256).where(
                Team.slug == slug,
                Team.state == "active",
                Team.avatar_jpeg.is_not(None),
            )
        )
    ).one_or_none()
    if row is None or row.avatar_jpeg is None or row.avatar_sha256 is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Изображение команды не найдено")
    etag = f'"{row.avatar_sha256}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    return Response(
        row.avatar_jpeg,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": etag,
            "X-Content-Type-Options": "nosniff",
        },
    )
