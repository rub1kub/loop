import asyncio
import hashlib
import secrets
from uuid import uuid4

from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultPhoto
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from redis.exceptions import RedisError, WatchError
from sqlalchemy import select

from ...database import utc_now
from ...dependencies import Config, ControlWallet, CurrentUser, Db, require_full_access
from ..teams.service import as_utc
from .card import render_card
from .models import PixelModeration, PixelRound, PixelShare
from .schemas import (
    PixelModerationRequest,
    PixelModerationView,
    PixelPlaceRequest,
    PixelReceipt,
    PixelRoundView,
    PixelScores,
    PixelShareRequest,
    PixelShareView,
    PixelState,
)
from .service import ensure_round, place, recolor, round_view, scores, state_view

router = APIRouter(prefix="/pixels", tags=["PIXELS"], dependencies=[Depends(require_full_access)])
public_router = APIRouter(prefix="/pixel-cards", tags=["PIXELS"])
control_router = APIRouter(prefix="/control/pixels", tags=["PIXELS control"])
CHANNEL = "loop:pixels:changed"


async def read_budget(request: Request, user_id: str, settings: Config) -> None:
    if settings.app_env != "production":
        return
    bucket = int(utc_now().timestamp()) // 60
    try:
        async with asyncio.timeout(0.5):
            async with request.app.state.redis.pipeline(transaction=True) as pipeline:
                key = f"loop:pixels:read:{user_id}:{bucket}"
                pipeline.incr(key)
                pipeline.expire(key, 90)
                count, _ = await pipeline.execute()
    except (RedisError, TimeoutError):
        return
    if int(count) > 120:
        raise HTTPException(429, "Слишком частое обновление полотна", headers={"Retry-After": "10"})


def enabled(settings: Config) -> None:
    if not settings.pixel_battle_enabled:
        raise HTTPException(409, "Полотно пока закрыто")


async def publish(request: Request) -> None:
    try:
        async with asyncio.timeout(0.5):
            await request.app.state.redis.publish(CHANNEL, "changed")
    except (RedisError, TimeoutError):
        # Delivery only speeds up reads; the committed database remains authoritative.
        pass


async def wait_for_change(
    request: Request,
    db: Db,
    user_id: str,
    round_id: str,
    after: int,
    wait: int,
) -> None:
    # Release the auth/read transaction. Cross-worker leases cap each person's open polls.
    await db.commit()
    lease_key: str | None = None
    lease = secrets.token_hex(12)
    try:
        async with asyncio.timeout(wait + 1):
            for slot in range(3):
                key = f"loop:pixels:watch:{user_id}:{slot}"
                if await request.app.state.redis.set(key, lease, ex=25, nx=True):
                    lease_key = key
                    break
            if lease_key is None:
                raise HTTPException(
                    429,
                    "Полотно уже открыто на нескольких устройствах",
                    headers={"Retry-After": "5"},
                )
            async with request.app.state.redis.pubsub() as subscription:
                await subscription.subscribe(CHANNEL)
                latest = await db.get(PixelRound, round_id, populate_existing=True)
                changed = latest is None or latest.revision != after
                await db.commit()
                if changed:
                    return
                deadline = asyncio.get_running_loop().time() + wait
                while (remaining := deadline - asyncio.get_running_loop().time()) > 0:
                    message = await subscription.get_message(
                        ignore_subscribe_messages=True, timeout=remaining
                    )
                    if message:
                        return
                    if await request.is_disconnected():
                        return
    except (RedisError, TimeoutError):
        # A bounded, ordinary snapshot also works through mobile/proxy handoffs.
        pass
    finally:
        if lease_key:
            try:
                async with asyncio.timeout(0.5):
                    async with request.app.state.redis.pipeline(transaction=True) as pipeline:
                        await pipeline.watch(lease_key)
                        if await pipeline.get(lease_key) == lease:
                            pipeline.multi()
                            pipeline.delete(lease_key)
                            await pipeline.execute()
            except (RedisError, WatchError, TimeoutError):
                pass


@router.get("", response_model=PixelState)
async def canvas(
    request: Request,
    response: Response,
    user: CurrentUser,
    db: Db,
    settings: Config,
    round_id: str | None = Query(default=None, max_length=10),
    after: int | None = Query(default=None, ge=0),
    wait: int = Query(default=0, ge=0, le=20),
) -> PixelState:
    response.headers["Cache-Control"] = "private, no-store"
    if not settings.pixel_battle_enabled:
        return PixelState(enabled=False, server_time=utc_now())
    user_id = user.id
    await read_budget(request, user_id, settings)
    board = await ensure_round(db, utc_now())
    if wait and round_id == board.id and after == board.revision:
        await wait_for_change(request, db, user_id, board.id, after, wait)
        # A new round may have begun while the request was waiting.
        db.expire_all()
        board = await ensure_round(db, utc_now())
    result = await state_view(
        db, board, user_id, utc_now(), after=after if round_id == board.id else None
    )
    await db.commit()
    return result


@router.post("/moves", response_model=PixelReceipt)
async def put_pixel(
    body: PixelPlaceRequest,
    request: Request,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> PixelReceipt:
    enabled(settings)
    result = await place(db, user, body)
    await db.commit()
    await publish(request)
    return result


async def get_round(db: Db, round_id: str) -> PixelRound:
    board = await db.get(PixelRound, round_id)
    if board is None:
        raise HTTPException(404, "Полотно не найдено")
    return board


@router.get("/archive", response_model=list[PixelRoundView])
async def archive(user: CurrentUser, db: Db) -> list[PixelRoundView]:
    del user
    at = utc_now()
    boards = await db.scalars(
        select(PixelRound)
        .where(PixelRound.ends_at <= at)
        .order_by(PixelRound.starts_at.desc())
        .limit(12)
    )
    return [round_view(board, at) for board in boards]


@router.get("/rounds/{round_id}", response_model=PixelState)
async def archived_canvas(round_id: str, user: CurrentUser, db: Db) -> PixelState:
    return await state_view(db, await get_round(db, round_id), user.id, utc_now())


@router.get("/rounds/{round_id}/scores", response_model=PixelScores)
async def leaderboard(round_id: str, user: CurrentUser, db: Db) -> PixelScores:
    return await scores(db, await get_round(db, round_id), user.id)


@router.get("/rounds/{round_id}/moderation", response_model=list[PixelModerationView])
async def moderation_log(round_id: str, user: CurrentUser, db: Db) -> list[PixelModerationView]:
    del user
    rows = await db.scalars(
        select(PixelModeration)
        .where(PixelModeration.round_id == round_id)
        .order_by(PixelModeration.created_at.desc())
        .limit(100)
    )
    return [
        PixelModerationView(
            id=row.id,
            reason=row.reason,
            x=row.x,
            y=row.y,
            width=row.width,
            height=row.height,
            created_at=as_utc(row.created_at),
        )
        for row in rows
    ]


@control_router.post("/clear", status_code=204)
async def clear_area(
    body: PixelModerationRequest,
    request: Request,
    wallet: ControlWallet,
    db: Db,
) -> Response:
    if body.x + body.width > 128 or body.y + body.height > 128:
        raise HTTPException(422, "Область выходит за границы полотна")
    board = await db.scalar(
        select(PixelRound)
        .where(PixelRound.id == body.round_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    at = utc_now()
    if board is None or at >= as_utc(board.ends_at):
        raise HTTPException(409, "Архивное полотно нельзя изменить")
    previous = await db.get(PixelModeration, str(body.operation_id))
    if previous:
        if (
            previous.round_id,
            previous.x,
            previous.y,
            previous.width,
            previous.height,
            previous.reason,
        ) != (body.round_id, body.x, body.y, body.width, body.height, body.reason):
            raise HTTPException(409, "Эта операция уже применена к другой области")
        return Response(status_code=204)
    db.add(
        PixelModeration(
            id=str(body.operation_id),
            round_id=board.id,
            actor_hash=hashlib.sha256(wallet.encode()).hexdigest(),
            reason=body.reason,
            x=body.x,
            y=body.y,
            width=body.width,
            height=body.height,
            created_at=at,
        )
    )
    for y in range(body.y, body.y + body.height):
        for x in range(body.x, body.x + body.width):
            await recolor(
                db, board, y * 128 + x, 0, at, user_id=None, team_id=None, operation_id=str(uuid4())
            )
    await db.commit()
    await publish(request)
    return Response(status_code=204)


@router.post("/share", response_model=PixelShareView)
async def prepare_share(
    body: PixelShareRequest,
    request: Request,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> PixelShareView:
    enabled(settings)
    board = await get_round(db, body.round_id)
    # Serialize preparation per person; reuse a recent card to bound image storage.
    from ...models import User

    await db.scalar(select(User).where(User.id == user.id).with_for_update())
    latest = await db.scalar(
        select(PixelShare)
        .where(PixelShare.user_id == user.id)
        .order_by(PixelShare.created_at.desc())
        .limit(1)
    )
    at = utc_now()
    if latest and (at - as_utc(latest.created_at)).total_seconds() < 30:
        if (latest.round_id, latest.x, latest.y) != (body.round_id, body.x, body.y):
            raise HTTPException(
                429,
                "Новый фрагмент можно отправить через 30 секунд",
                headers={"Retry-After": "30"},
            )
        share = latest
    else:
        share = PixelShare(
            id=secrets.token_urlsafe(18),
            user_id=user.id,
            round_id=board.id,
            revision=board.revision,
            x=body.x,
            y=body.y,
            image=render_card(board.pixels, body.x, body.y),
            created_at=at,
        )
        db.add(share)
        await db.flush()
    url = f"https://t.me/{settings.bot_username}?startapp=pixel_{share.id}"
    image_url = f"{settings.public_origin}/api/v1/pixel-cards/{share.id}.jpg"
    await db.commit()
    prepared_id = None
    if request.app.state.bot and settings.bot_username:
        try:
            async with asyncio.timeout(8):
                prepared = await request.app.state.bot.save_prepared_inline_message(
                    user_id=user.telegram_id,
                    result=InlineQueryResultPhoto(
                        id=f"pixel-{share.id}",
                        photo_url=image_url,
                        thumbnail_url=image_url,
                        caption="Помоги дорисовать. Один пиксель каждые 30 секунд — бесплатно.",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[
                                [InlineKeyboardButton(text="Открыть полотно", url=url)]
                            ]
                        ),
                    ),
                    allow_user_chats=True,
                    allow_bot_chats=False,
                    allow_group_chats=True,
                    allow_channel_chats=True,
                )
                prepared_id = prepared.id
        except (TelegramAPIError, TimeoutError):
            pass
    return PixelShareView(url=url, image_url=image_url, prepared_message_id=prepared_id)


@router.get("/shares/{share_id}", response_model=PixelShareRequest)
async def shared_region(share_id: str, user: CurrentUser, db: Db) -> PixelShareRequest:
    del user
    share = await db.get(PixelShare, share_id)
    if share is None:
        raise HTTPException(404, "Фрагмент не найден")
    return PixelShareRequest(round_id=share.round_id, x=share.x, y=share.y)


@public_router.get("/{share_id}.jpg", include_in_schema=False)
async def share_image(share_id: str, db: Db) -> Response:
    data = await db.scalar(select(PixelShare.image).where(PixelShare.id == share_id))
    if data is None:
        raise HTTPException(404, "Карточка не найдена")
    return Response(
        data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=86400, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
