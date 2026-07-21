import re
import secrets
from datetime import UTC, datetime, timedelta

from aiogram import Bot, Dispatcher, Router
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
from .models import InlineInvite

INLINE_PATTERN = re.compile(r"^\s*(\d+(?:\.\d{1,9})?)\s+(25|50|75)\s*$")


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
        await message.answer("LOOP\nТвой кошелёк. Твои средства.", reply_markup=keyboard)

    @router.inline_query()
    async def inline_duel(query: InlineQuery) -> None:
        match = INLINE_PATTERN.match(query.query)
        if not match:
            await query.answer([], cache_time=1, is_personal=True)
            return
        whole, fractional = (match.group(1).split(".", 1) + [""])[:2]
        stake_nano = int(whole) * 1_000_000_000 + int(fractional.ljust(9, "0"))
        chance = int(match.group(2))
        chance_bps = chance * 100
        if stake_nano * 10_000 % chance_bps:
            await query.answer([], cache_time=1, is_personal=True)
            return
        total_pool = stake_nano * 10_000 // chance_bps
        if not settings.min_pool_nano <= total_pool <= settings.max_pool_nano:
            await query.answer([], cache_time=1, is_personal=True)
            return
        code = secrets.token_urlsafe(9)
        expires = datetime.now(UTC) + timedelta(hours=1)
        async with session_factory() as db:
            active_invites = await db.scalar(
                select(func.count())
                .select_from(InlineInvite)
                .where(
                    InlineInvite.creator_telegram_id == query.from_user.id,
                    InlineInvite.expires_at > datetime.now(UTC),
                )
            )
            if (active_invites or 0) >= 20:
                await query.answer([], cache_time=1, is_personal=True)
                return
            db.add(
                InlineInvite(
                    code=code,
                    creator_telegram_id=query.from_user.id,
                    stake_nano=stake_nano,
                    chance_bps=chance_bps,
                    expires_at=expires,
                )
            )
            await db.commit()
        deep_link = f"https://t.me/{settings.bot_username}?startapp=duel_{code}"
        article = InlineQueryResultArticle(
            id=code,
            title="LOOP DUEL",
            description=f"{match.group(1)} GRAM · шанс {chance}%",
            input_message_content=InputTextMessageContent(
                message_text=(
                    f"LOOP DUEL\n\nИгрок вызывает тебя.\n"
                    f"Ставка: {match.group(1)} GRAM\nШанс: {100 - chance}%"
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
    await bot.set_webhook(
        webhook_url,
        secret_token=settings.telegram_webhook_secret.get_secret_value(),
        allowed_updates=["message", "inline_query", "callback_query"],
        drop_pending_updates=False,
    )
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="LOOP", web_app=WebAppInfo(url=settings.public_origin))
    )
