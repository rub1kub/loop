from datetime import UTC, datetime, timedelta

from aiogram.exceptions import TelegramAPIError
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from .dependencies import Config, CurrentUser, Db
from .models import ResultCard
from .referrals import get_or_create_referral_code
from .result_cards import (
    CardFacts,
    build_result_inline,
    duel_opponent_label,
    render_result_card,
)
from .schemas import PreparedResultShareView, ResultCardView

router = APIRouter(prefix="/api/v1/results", tags=["results"])


def card_view(card: ResultCard, settings: Config) -> ResultCardView:
    return ResultCardView(
        id=card.id,
        mode=card.mode,
        payout_nano=card.payout_nano,
        contributed_nano=card.contributed_nano,
        result_nano=card.result_nano,
        queue_position=card.queue_position,
        proof_url=card.proof_url,
        image_url=f"{settings.public_origin}/api/v1/results/cards/{card.public_id}.jpg",
        seen_at=card.seen_at,
        created_at=card.created_at,
    )


async def owned_card(db: Db, card_id: str, user_id: str) -> ResultCard:
    card = await db.scalar(
        select(ResultCard).where(ResultCard.id == card_id, ResultCard.user_id == user_id)
    )
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "result not found")
    return card


@router.get("", response_model=list[ResultCardView])
async def list_results(
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> list[ResultCardView]:
    cards = (
        await db.scalars(
            select(ResultCard)
            .where(ResultCard.user_id == user.id)
            .order_by(ResultCard.created_at.desc())
            .limit(20)
        )
    ).all()
    return [card_view(card, settings) for card in cards]


@router.get("/cards/{public_id}.jpg", include_in_schema=False)
async def result_image(public_id: str, db: Db) -> Response:
    if not 20 <= len(public_id) <= 32 or not all(
        character.isalnum() or character in "-_" for character in public_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "result not found")
    card = await db.scalar(select(ResultCard).where(ResultCard.public_id == public_id))
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "result not found")
    content = await run_in_threadpool(
        render_result_card,
        CardFacts(
            public_id=card.public_id,
            mode=card.mode,
            payout_nano=card.payout_nano,
            contributed_nano=card.contributed_nano,
            result_nano=card.result_nano,
            queue_position=card.queue_position,
            opponent=await duel_opponent_label(db, card),
        )
    )
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/{card_id}/seen", response_model=ResultCardView)
async def mark_result_seen(
    card_id: str,
    user: CurrentUser,
    db: Db,
    settings: Config,
) -> ResultCardView:
    card = await owned_card(db, card_id, user.id)
    if card.seen_at is None:
        card.seen_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(card)
    return card_view(card, settings)


@router.post("/{card_id}/prepare", response_model=PreparedResultShareView)
async def prepare_result_share(
    card_id: str,
    user: CurrentUser,
    db: Db,
    settings: Config,
    request: Request,
) -> PreparedResultShareView:
    card = await owned_card(db, card_id, user.id)
    bot = request.app.state.bot
    if bot is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram sharing is unavailable"
        )
    try:
        referral = await get_or_create_referral_code(db, user.id)
    except RuntimeError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Telegram sharing is temporarily unavailable",
        ) from exc
    try:
        prepared = await bot.save_prepared_inline_message(
            user_id=user.telegram_id,
            result=build_result_inline(
                card,
                settings,
                referral.code,
                await duel_opponent_label(db, card),
            ),
            allow_user_chats=True,
            allow_bot_chats=False,
            allow_group_chats=True,
            allow_channel_chats=True,
        )
    except TelegramAPIError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram sharing is temporarily unavailable"
        ) from exc
    expiration = prepared.expiration_date
    if isinstance(expiration, int):
        expiration = datetime.fromtimestamp(expiration, UTC)
    elif isinstance(expiration, timedelta):
        expiration = datetime.now(UTC) + expiration
    elif expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=UTC)
    card.share_prepared_count += 1
    await db.commit()
    return PreparedResultShareView(
        prepared_message_id=prepared.id,
        expiration_date=expiration,
        fallback_query=f"result {card.public_id}",
    )
