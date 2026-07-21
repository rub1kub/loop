import asyncio
import re
import secrets
from datetime import UTC, datetime, timedelta

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings
from .cycles import as_utc, record_cycle_event
from .models import (
    ChallengeState,
    CycleEventKind,
    DuelChallenge,
    MatchmakingOffer,
    OfferState,
    ProofType,
    User,
)

INLINE_PATTERN = re.compile(r"^\s*duel\s+(\d{1,16})\s*$", re.IGNORECASE)


def format_gram(nano: int) -> str:
    value = nano / 1_000_000_000
    return f"{value:.9f}".rstrip("0").rstrip(".")


def create_dispatcher(
    settings: Settings, session_factory: async_sessionmaker[AsyncSession]
) -> Dispatcher:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="ОТКРЫТЬ LOOP", web_app=WebAppInfo(url=settings.public_origin)
                    )
                ]
            ]
        )
        await message.answer("LOOP\nЖивой цикл начинается здесь.", reply_markup=keyboard)

    @router.inline_query()
    async def inline_duel(query: InlineQuery) -> None:
        match = INLINE_PATTERN.match(query.query)
        if not match:
            await query.answer([], cache_time=1, is_personal=True)
            return
        offer_id = int(match.group(1))
        async with session_factory() as db:
            creator = await db.scalar(
                select(User).where(User.telegram_id == query.from_user.id)
            )
            if creator is None:
                await query.answer([], cache_time=1, is_personal=True)
                return
            offer = await db.scalar(
                select(MatchmakingOffer).where(
                    MatchmakingOffer.user_id == creator.id,
                    MatchmakingOffer.onchain_offer_id == offer_id,
                    MatchmakingOffer.network == settings.ton_network_id,
                    MatchmakingOffer.contract_address == settings.ton_contract_address,
                    MatchmakingOffer.chance_bps == 5_000,
                    MatchmakingOffer.state == OfferState.OPEN.value,
                    MatchmakingOffer.expires_at > datetime.now(UTC),
                )
            )
            if offer is None:
                await query.answer([], cache_time=1, is_personal=True)
                return
            challenge = await db.scalar(
                select(DuelChallenge).where(DuelChallenge.creator_offer_id == offer.id)
            )
            active_challenges = await db.scalar(
                select(func.count())
                .select_from(DuelChallenge)
                .where(
                    DuelChallenge.creator_user_id == creator.id,
                    DuelChallenge.state.in_(
                        [ChallengeState.OPEN.value, ChallengeState.ACCEPTED.value]
                    ),
                    DuelChallenge.expires_at > datetime.now(UTC),
                )
            )
            if challenge is None and (active_challenges or 0) >= 20:
                await query.answer([], cache_time=1, is_personal=True)
                return
            if challenge is None:
                challenge = DuelChallenge(
                    code=secrets.token_urlsafe(9),
                    creator_user_id=creator.id,
                    creator_offer_id=offer.id,
                    expires_at=min(
                        as_utc(offer.expires_at),
                        datetime.now(UTC) + timedelta(hours=1),
                    ),
                )
                db.add(challenge)
                await db.flush()
                await record_cycle_event(
                    db,
                    user_id=creator.id,
                    actor_user_id=creator.id,
                    kind=CycleEventKind.INVITE_CREATED,
                    title="Вызов отправлен",
                    proof_type=ProofType.TELEGRAM,
                    proof_ref=challenge.code,
                    dedupe_key=f"challenge-created:{challenge.code}",
                )
            await db.commit()
        amount = format_gram(offer.stake_nano)
        deep_link = f"https://t.me/{settings.bot_username}?startapp=duel_{challenge.code}"
        article = InlineQueryResultArticle(
            id=challenge.code,
            title="LOOP DUEL",
            description=f"{amount} GRAM · равные условия",
            input_message_content=InputTextMessageContent(
                message_text=(
                    f"LOOP DUEL\n\n{creator.first_name} бросает тебе вызов.\n\n"
                    f"Вклад: {amount} GRAM\nУсловия: 50 / 50\n\n"
                    "Прими вызов и подтверди участие в LOOP."
                )
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="ПРИНЯТЬ", url=deep_link)]]
            ),
        )
        await query.answer([article], cache_time=1, is_personal=True)

    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return dispatcher


async def configure_bot(bot: Bot, settings: Settings) -> None:
    webhook_url = f"{settings.public_origin}{settings.webhook_path}"
    for attempt in range(3):
        try:
            await bot.set_webhook(
                webhook_url,
                secret_token=settings.telegram_webhook_secret.get_secret_value(),
                allowed_updates=["message", "inline_query", "callback_query"],
                drop_pending_updates=False,
            )
            break
        except TelegramRetryAfter as exc:
            if attempt == 2:
                raise
            await asyncio.sleep(float(exc.retry_after) + 0.25)
    for attempt in range(3):
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="LOOP", web_app=WebAppInfo(url=settings.public_origin)
                )
            )
            break
        except TelegramRetryAfter as exc:
            if attempt == 2:
                raise
            await asyncio.sleep(float(exc.retry_after) + 0.25)
