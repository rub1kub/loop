import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.filters import Command, CommandStart
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
    "LOOP — живой цикл внутри Telegram. В BANK новые взносы постепенно наполняют "
    "более ранние позиции прозрачной очереди. В DUEL два участника принимают "
    "равный вызов один на один. Рейтинг показывает завершённые циклы и надёжность. "
    "Все действия подтверждаются внешним TON-кошельком."
)
BOT_SHORT_DESCRIPTION = (
    "Живой цикл: очередь BANK, равные DUEL один на один и рейтинг подтверждённых действий."
)
BOT_MENU_TEXT = "Открыть LOOP"
BOT_COMMANDS = [
    BotCommand(command="start", description="Открыть LOOP"),
    BotCommand(command="support", description="Помощь и связь"),
]
START_MESSAGES = (
    "∞ LOOP\n\nЦикл уже идёт.\n\nBANK — войди в очередь.\n"
    "DUEL — брось вызов.\n\nТвой ход.",
    "∞ LOOP\n\nОдин цикл. Два пути.\n\nBANK — дождись момента.\n"
    "DUEL — создай его.\n\nВойти?",
    "∞ LOOP\n\nЗдесь всё движется дальше.\n\nBANK — займи место.\n"
    "DUEL — выбери соперника.\n\nПродолжить?",
    "∞ LOOP\n\nКруг уже замкнулся.\n\nBANK — стань частью очереди.\n"
    "DUEL — выйди один на один.\n\nТвой ход.",
    "∞ LOOP\n\nНичего не стоит на месте.\n\nBANK — очередь движется.\n"
    "DUEL — вызов начинается с тебя.\n\nВойти.",
    "∞ LOOP\n\nТы не первый. И не последний.\n\nBANK — войди в очередь.\n"
    "DUEL — встреть соперника.\n\nПродолжить цикл.",
    "∞ LOOP\n\nУ каждого хода есть продолжение.\n\nBANK — займи позицию.\n"
    "DUEL — брось вызов.\n\nЧто выберешь?",
    "∞ LOOP\n\nЦикл не ждёт.\n\nBANK — место в очереди.\n"
    "DUEL — встреча один на один.\n\nВойти.",
    "∞ LOOP\n\nДальше решает твой ход.\n\nBANK — войди в поток.\n"
    "DUEL — найди равного.\n\nLOOP открыт.",
    "∞ LOOP\n\nВсё возвращается. Но не прежним.\n\nBANK — очередь.\n"
    "DUEL — вызов.\n\nПродолжить.",
    "∞ LOOP\n\nЗдесь действие всегда имеет продолжение.\n\nBANK — займи место.\n"
    "DUEL — сделай вызов.\n\nТвой ход.",
    "∞ LOOP\n\nДва выбора. Один след.\n\nBANK — в очередь.\n"
    "DUEL — один на один.\n\nВойти.",
    "∞ LOOP\n\nЦикл начинается не с нуля.\n\nBANK — продолжи очередь.\n"
    "DUEL — начни встречу.\n\nВойти в LOOP.",
    "∞ LOOP\n\nСначала — один ход. Потом — цикл.\n\nBANK — займи место.\n"
    "DUEL — брось вызов.\n\nНачать.",
    "∞ LOOP\n\nОчередь или вызов.\n\nBANK — терпение.\n"
    "DUEL — решимость.\n\nОба ведут дальше.",
    "∞ LOOP\n\nЗдесь никто не остаётся вне цикла.\n\nBANK — войди в очередь.\n"
    "DUEL — выйди навстречу.\n\nТвой ход.",
    "∞ LOOP\n\nВнутри всё проще, чем кажется.\n\nBANK — очередь.\n"
    "DUEL — вызов.\n\nОткрой LOOP.",
    "∞ LOOP\n\nОдин шаг меняет следующий.\n\nBANK — займи позицию.\n"
    "DUEL — найди соперника.\n\nПродолжить.",
    "∞ LOOP\n\nЦикл видит каждый ход.\n\nBANK — очередь.\n"
    "DUEL — один на один.\n\nВойти.",
    "∞ LOOP\n\nТишина длится до первого хода.\n\nBANK — войди в очередь.\n"
    "DUEL — брось вызов.\n\nНачать.",
    "∞ LOOP\n\nНе наблюдай за циклом.\n\nBANK — займи место.\n"
    "DUEL — сделай вызов.\n\nСтань его частью.",
    "∞ LOOP\n\nСледующий ход уже за тобой.\n\nBANK — очередь ждёт.\n"
    "DUEL — соперник найдётся.\n\nВойти.",
    "∞ LOOP\n\nУ LOOP нет последнего хода.\n\nBANK — продолжи очередь.\n"
    "DUEL — начни вызов.\n\nВойти.",
    "∞ LOOP\n\nДва режима. Одно движение.\n\nBANK — войди в очередь.\n"
    "DUEL — выйди один на один.\n\nТвой ход.",
    "∞ LOOP\n\nМесто в цикле не дают. Его занимают.\n\nBANK — очередь.\n"
    "DUEL — вызов.\n\nВойти.",
    "∞ LOOP\n\nВсё начинается после нажатия.\n\nBANK — очередь.\n"
    "DUEL — вызов.\n\nОткрыть LOOP.",
    "∞ LOOP\n\nТы уже у входа.\n\nBANK — займи место.\n"
    "DUEL — выбери соперника.\n\nОстался один ход.",
    "∞ LOOP\n\nЦикл не объясняют. В него входят.\n\nBANK — очередь.\n"
    "DUEL — вызов.\n\nВойти.",
    "∞ LOOP\n\nЗа каждым действием — следующее.\n\nBANK — место в очереди.\n"
    "DUEL — один на один.\n\nПродолжить.",
    "∞ LOOP\n\nПравила просты. Цикл — нет.\n\nBANK — очередь.\n"
    "DUEL — вызов.\n\nТвой ход.",
    "∞ LOOP\n\nВремя идёт вперёд. LOOP — по кругу.\n\nBANK — займи место.\n"
    "DUEL — встреть соперника.\n\nВойти.",
    "∞ LOOP\n\nДо следующего хода — один шаг.\n\nBANK — войди в очередь.\n"
    "DUEL — выйди один на один.\n\nОткрыть.",
)
SUPPORT_TEXT = (
    "ПОДДЕРЖКА LOOP\n\n"
    "Если действие зависло или результат не обновился:\n\n"
    "1. Не отправляй транзакцию повторно.\n"
    "2. Сделай снимок экрана.\n"
    "3. Скопируй адрес кошелька и хэш транзакции, если он появился.\n"
    "4. Напиши, где возникла проблема: BANK, DUEL, рейтинг или вход.\n\n"
    "Никому не отправляй seed-фразу, приватный ключ, пароль или код из Telegram. "
    "Поддержка LOOP никогда их не запрашивает.\n\n"
    "Нажми кнопку ниже и отправь собранные данные."
)


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def format_gram(nano: int) -> str:
    value = nano / 1_000_000_000
    return f"{value:.9f}".rstrip("0").rstrip(".")


def main_app_deep_link(bot_username: str) -> str:
    return f"https://t.me/{bot_username.removeprefix('@')}?startapp"


def start_message_for(user_id: int, on_date: date | None = None) -> str:
    current_date = on_date or datetime.now(UTC).date()
    return START_MESSAGES[(user_id + current_date.toordinal()) % len(START_MESSAGES)]


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
        user_id = message.from_user.id if message.from_user is not None else 0
        await message.answer(start_message_for(user_id), reply_markup=keyboard)

    @router.message(Command("support"))
    async def support(message: Message) -> None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="НАПИСАТЬ В ПОДДЕРЖКУ", url=settings.support_url)],
                [
                    InlineKeyboardButton(
                        text="ВЕРНУТЬСЯ В LOOP",
                        url=main_app_deep_link(settings.bot_username),
                    )
                ],
            ]
        )
        await message.answer(SUPPORT_TEXT, reply_markup=keyboard)

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
                # The address-bound direct flow creates the invitation id before the creator signs
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

    current_commands = await bot.get_my_commands()
    if [(item.command, item.description) for item in current_commands] != [
        (item.command, item.description) for item in BOT_COMMANDS
    ]:
        await apply_bot_setting(lambda: bot.set_my_commands(BOT_COMMANDS))

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
