import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import CommandStart
from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings
from .models import User
from .modules.duel.models import (
    ChallengeState,
    DuelChallenge,
    MatchmakingOffer,
    OfferState,
)

INLINE_PATTERN = re.compile(r"^\s*duel\s+(\d{1,16})\s*$", re.IGNORECASE)
BOT_NAME = "LOOP"
BOT_DESCRIPTION = (
    "LOOP — два независимых режима в TON. BANK — очередь позиций по порядку. "
    "DUEL — равные вызовы между игроками 50/50."
)
BOT_SHORT_DESCRIPTION = "BANK и равные вызовы DUEL на GRAM."
BOT_MENU_TEXT = "Открыть LOOP"


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def format_gram(nano: int) -> str:
    value = nano / 1_000_000_000
    return f"{value:.9f}".rstrip("0").rstrip(".")


def main_app_deep_link(bot_username: str) -> str:
    return f"https://t.me/{bot_username.removeprefix('@')}?startapp"


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
                        text="ОТКРЫТЬ LOOP", url=main_app_deep_link(settings.bot_username)
                    )
                ]
            ]
        )
        await message.answer("LOOP\nBANK и DUEL открыты.", reply_markup=keyboard)

    @router.inline_query()
    async def inline_duel(query: InlineQuery) -> None:
        match = INLINE_PATTERN.match(query.query)
        if not match:
            await query.answer([], cache_time=1, is_personal=True)
            return
        offer_id = int(match.group(1))
        async with session_factory() as db:
            creator = await db.scalar(select(User).where(User.telegram_id == query.from_user.id))
            if creator is None:
                await query.answer([], cache_time=1, is_personal=True)
                return
            offer = await db.scalar(
                select(MatchmakingOffer).where(
                    MatchmakingOffer.user_id == creator.id,
                    MatchmakingOffer.onchain_offer_id == offer_id,
                    MatchmakingOffer.network == settings.ton_network_id,
                    MatchmakingOffer.contract_address == settings.effective_duel_contract_address,
                    MatchmakingOffer.mode == "direct",
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
            if challenge is not None and (
                challenge.state != ChallengeState.OPEN.value
                or as_utc(challenge.expires_at) <= datetime.now(UTC)
            ):
                await query.answer([], cache_time=1, is_personal=True)
                return
            if challenge is None:
                # V1.1 creates the invitation id before the creator signs the
                # on-chain offer. Generating it here would not be covered by
                # the contract's address-bound acceptance permit.
                await query.answer([], cache_time=1, is_personal=True)
                return
            await db.commit()
        amount = format_gram(offer.opponent_stake_nano)
        receiver_chance = 10_000 - offer.chance_bps
        display_terms = f"{receiver_chance // 100}/{offer.chance_bps // 100}"
        profit = format_gram(offer.payout_nano - offer.opponent_stake_nano)
        deep_link = f"https://t.me/{settings.bot_username}?startapp=duel_{challenge.code}"
        article = InlineQueryResultArticle(
            id=challenge.code,
            title="LOOP DUEL",
            description=f"Внести {amount} GRAM · условия {display_terms}",
            input_message_content=InputTextMessageContent(
                message_text=(
                    f"LOOP DUEL\n\n{creator.first_name} бросает тебе вызов.\n\n"
                    f"Твоя ставка: {amount} GRAM\n"
                    f"Условия: {display_terms}\n"
                    f"Разница при победе: {profit} GRAM\n\n"
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


async def apply_bot_setting(operation: Callable[[], Awaitable[bool]]) -> None:
    for attempt in range(3):
        try:
            await operation()
            return
        except TelegramRetryAfter as exc:
            if attempt == 2:
                raise
            await asyncio.sleep(float(exc.retry_after) + 0.25)


async def configure_bot(bot: Bot, settings: Settings) -> None:
    webhook_url = f"{settings.public_origin}{settings.webhook_path}"
    allowed_updates = ["message", "inline_query", "callback_query"]
    webhook = await bot.get_webhook_info()
    if webhook.url != webhook_url or set(webhook.allowed_updates or []) != set(allowed_updates):
        await apply_bot_setting(
            lambda: bot.set_webhook(
                webhook_url,
                secret_token=settings.telegram_webhook_secret.get_secret_value(),
                allowed_updates=allowed_updates,
                drop_pending_updates=False,
            )
        )

    if (await bot.get_my_name()).name != BOT_NAME:
        await apply_bot_setting(lambda: bot.set_my_name(BOT_NAME))
    if (await bot.get_my_description()).description != BOT_DESCRIPTION:
        await apply_bot_setting(lambda: bot.set_my_description(BOT_DESCRIPTION))
    if (await bot.get_my_short_description()).short_description != BOT_SHORT_DESCRIPTION:
        await apply_bot_setting(lambda: bot.set_my_short_description(BOT_SHORT_DESCRIPTION))

    expected_commands = [BotCommand(command="start", description="Открыть LOOP")]
    current_commands = await bot.get_my_commands()
    if [(item.command, item.description) for item in current_commands] != [
        (item.command, item.description) for item in expected_commands
    ]:
        await apply_bot_setting(lambda: bot.set_my_commands(expected_commands))

    menu = await bot.get_chat_menu_button()
    if (
        not isinstance(menu, MenuButtonWebApp)
        or menu.text != BOT_MENU_TEXT
        or menu.web_app.url.rstrip("/") != settings.public_origin.rstrip("/")
    ):
        await apply_bot_setting(
            lambda: bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text=BOT_MENU_TEXT,
                    web_app=WebAppInfo(url=settings.public_origin),
                ),
            )
        )
