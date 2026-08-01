import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog
from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputRichBlockDivider,
    InputRichBlockList,
    InputRichBlockListItem,
    InputRichBlockParagraph,
    InputRichBlockTable,
    InputRichBlockUnion,
    InputRichMessage,
    InputTextMessageContent,
    MenuButtonWebApp,
    Message,
    RichBlockTableCell,
    RichTextBold,
    WebAppInfo,
)
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .config import Settings
from .models import ResultCard, User
from .modules.duel.models import (
    ChallengeState,
    DuelChallenge,
    MatchmakingOffer,
    OfferState,
)
from .referrals import get_or_create_referral_code
from .result_cards import build_result_inline

logger = structlog.get_logger()

INLINE_PATTERN = re.compile(r"^\s*duel\s+(\d{1,16})\s*$", re.IGNORECASE)
RESULT_PATTERN = re.compile(r"^\s*result\s+([A-Za-z0-9_-]{20,32})\s*$", re.IGNORECASE)
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
START_MESSAGE_COUNTER_TTL_SECONDS = 90 * 24 * 60 * 60
START_MESSAGES = (
    "∞ LOOP\n\nBANK — открыто признанная финансовая пирамида.\nDUEL — открыто признанная азартная"
    " игра.\n\n"
    "Честно, редкость.",
    "∞ LOOP\n\nBANK копит очередь. DUEL решает два числа против двух чисел.\n\n"
    "Ничего сложного, кроме денег.",
    "∞ LOOP\n\nDUEL — 50 на 50, без обмана. BANK — очередь, без иллюзий.\n\nВыбирай яд.",
    "∞ LOOP\n\nBANK — вставай в очередь. DUEL — вызывай на дуэль.\n\nВ обоих можно потерять всё.",
    "∞ LOOP\n\nПирамида (BANK) и дуэль (DUEL) под одной крышей.\n\nКод открыт, риск тоже.",
    "∞ LOOP\n\nDUEL — шанс 50/50. BANK — шанс зависит от очереди.\n\n"
    "Оба варианта честнее, чем кажется.",
    "∞ LOOP\n\nBANK не обещает выплату. DUEL не обещает победу.\n\n"
    "Зато оба обещают честный расчёт.",
    "∞ LOOP\n\nЗдесь два способа расстаться с GRAM: медленно (BANK) и быстро (DUEL).\n\n"
    "Выбор за тобой.",
    "∞ LOOP\n\nBANK — очередь на выплату, которой может не быть.\nDUEL — дуэль, где выигрывает"
    " один.\n\n"
    "Входи с открытыми глазами.",
    "∞ LOOP\n\nDUEL решает за 50/50. BANK решает за счёт следующих.\n\n"
    "Оба варианта на цепочке, оба проверяемы.",
    "∞ LOOP\n\nBANK — пирамида. DUEL — дуэль. Мы это не скрываем.\n\nОстальное решаешь сам.",
    "∞ LOOP\n\nDUEL — один против одного, судья — два заранее скрытых числа.\nBANK — ты против"
    " очереди.\n\n"
    "Войти?",
    "∞ LOOP\n\nЗдесь ничего не растёт само. Либо BANK, либо DUEL.\n\nОба варианта — на твой страх.",
    "∞ LOOP\n\nBANK копит. DUEL решает сразу. Общее одно: газ у тебя есть?\n\nТогда заходи.",
    "∞ LOOP\n\nDUEL — быстрый способ проверить удачу. BANK — медленный способ проверить"
    " терпение.\n\n"
    "Что сегодня?",
    "∞ LOOP\n\nПравила BANK и DUEL публичны, как и код. Незнание себя не спасёт.\n\n"
    "Но хотя бы честно.",
    "∞ LOOP\n\nDUEL никого не жалеет. BANK никому не должен.\n\nЗато оба на виду.",
    "∞ LOOP\n\nBANK растёт очередью, DUEL — ставками. Ты растёшь рисками.\n\nВойти в LOOP.",
    "∞ LOOP\n\nОдин против одного (DUEL) или один в очереди (BANK).\n\nВ обоих случаях платишь ты.",
    "∞ LOOP\n\nDUEL: 50/50, без историй про везение. BANK: очередь, без историй про доходность.\n\n"
    "Твой ход.",
    "∞ LOOP\n\nЗдесь не обещают иксы. Здесь обещают показать код.\n\nBANK и DUEL ждут.",
    "∞ LOOP\n\nBANK — для тех, кто любит очереди. DUEL — для тех, кто любит риск здесь и"
    " сейчас.\n\n"
    "Выбирай.",
    "∞ LOOP\n\nDUEL решает пара чисел на цепочке. BANK решает следующий взнос.\n\n"
    "Оба варианта проверяемы, оба не гарантированы.",
    "∞ LOOP\n\nМы не зовём тебя разбогатеть. Мы зовём в BANK и DUEL.\n\n"
    "Разница есть, и она важная.",
    "∞ LOOP\n\nDUEL закончится за минуты. BANK может не закончиться никогда.\n\n"
    "Выбирай по терпению.",
    "∞ LOOP\n\nBANK — очередь без гарантий. DUEL — дуэль без пощады.\n\nОба — LOOP.",
    "∞ LOOP\n\n"
    "Если зашёл за быстрым профитом — это не сюда.\nЕсли зашёл понять, как работает BANK и DUEL —"
    " сюда.",
    "∞ LOOP\n\nDUEL против соперника. BANK против времени.\n\n"
    "В обоих можно проиграть всё, что внёс.",
    "∞ LOOP\n\nBANK не притворяется вкладом. DUEL не притворяется инвестицией.\n\n"
    "Оба — то, чем названы.",
    "∞ LOOP\n\nDUEL — дуэль на GRAM. BANK — очередь на GRAM.\n\n"
    "Оба пункта меню — риск, без вывесок про доходность.",
    "∞ LOOP\n\nЗдесь можно выиграть DUEL или дождаться BANK.\n\n"
    "А можно не дождаться. Так тоже бывает.",
    "∞ LOOP\n\nBANK и DUEL — на блокчейне, не на словах.\n\nПроверь код, потом заходи.",
    "∞ LOOP\n\nDUEL за минуту решает, кто прав. BANK решает медленнее и не всегда.\n\n"
    "Твой выбор, твой риск.",
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


def start_message_for(user_id: int, sequence: int) -> str:
    return START_MESSAGES[(user_id + sequence - 1) % len(START_MESSAGES)]


async def next_start_message(redis_client: Redis, user_id: int) -> str:
    key = f"loop:bot:start-message:{user_id}"
    sequence = int(await redis_client.incr(key))
    await redis_client.expire(key, START_MESSAGE_COUNTER_TTL_SECONDS)
    return start_message_for(user_id, sequence)


SUPPORT_STEP_PATTERN = re.compile(r"^\d+\.\s+(.*)$")


def _centered_box(text: str) -> InputRichBlockTable:
    """A bordered, centered one-cell table — the only place Bot API 10.1
    exposes text alignment at all (RichBlockTableCell.align). Every other
    block type renders left-aligned with no override.
    """
    return InputRichBlockTable(
        is_bordered=True,
        cells=[[RichBlockTableCell(align="center", valign="middle", text=RichTextBold(text=text))]],
    )


def build_start_rich_message(text: str) -> InputRichMessage:
    """Turn a plain START_MESSAGES entry into a structured rich message.

    Parses the "∞ LOOP\n\n{body}\n\n{cta}" shape the constant is written in,
    rather than hand-duplicating all 33 variants as block literals — the
    plain string stays the single source of truth, so editing START_MESSAGES
    is still the only thing anyone has to do.

    Only the opening "∞ LOOP" line renders as a centered, bordered box —
    everything after it, including the closing line, stays plain
    left-aligned text.
    """
    heading, *rest = text.split("\n\n")
    blocks: list[InputRichBlockUnion] = [_centered_box(heading)]
    for section in rest:
        for line in section.split("\n"):
            blocks.append(InputRichBlockParagraph(text=line))
    return InputRichMessage(blocks=blocks)


def build_support_rich_message(text: str) -> InputRichMessage:
    """Turn SUPPORT_TEXT's numbered plain-text steps into a real list block."""
    heading, intro, steps_block, warning, closing = text.split("\n\n")
    items: list[InputRichBlockListItem] = []
    for line in steps_block.split("\n"):
        match = SUPPORT_STEP_PATTERN.match(line)
        if match is None:
            raise ValueError(f"unexpected support step line: {line!r}")
        items.append(
            InputRichBlockListItem(
                value=len(items) + 1,
                blocks=[InputRichBlockParagraph(text=match.group(1))],
            )
        )
    return InputRichMessage(
        blocks=[
            _centered_box(heading),
            InputRichBlockParagraph(text=intro),
            InputRichBlockList(items=items),
            InputRichBlockDivider(),
            InputRichBlockParagraph(text=RichTextBold(text=warning)),
            InputRichBlockParagraph(text=closing),
        ]
    )


def create_dispatcher(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
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
        text = await next_start_message(redis_client, user_id)
        try:
            await message.answer_rich(build_start_rich_message(text), reply_markup=keyboard)
        except TelegramBadRequest as exc:
            logger.warning("start_rich_message_rejected", error=str(exc))
            await message.answer(text, reply_markup=keyboard)

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
        try:
            await message.answer_rich(
                build_support_rich_message(SUPPORT_TEXT), reply_markup=keyboard
            )
        except TelegramBadRequest as exc:
            logger.warning("support_rich_message_rejected", error=str(exc))
            await message.answer(SUPPORT_TEXT, reply_markup=keyboard)

    @router.inline_query()
    async def inline_result_or_duel(query: InlineQuery) -> None:
        result_match = RESULT_PATTERN.match(query.query)
        if result_match:
            async with session_factory() as db:
                creator = await db.scalar(
                    select(User).where(User.telegram_id == query.from_user.id)
                )
                if creator is None:
                    await query.answer([], cache_time=1, is_personal=True)
                    return
                card = await db.scalar(
                    select(ResultCard).where(
                        ResultCard.public_id == result_match.group(1),
                        ResultCard.user_id == creator.id,
                    )
                )
                referral = await get_or_create_referral_code(db, creator.id)
            if card is None:
                await query.answer([], cache_time=1, is_personal=True)
                return
            await query.answer(
                [
                    build_result_inline(
                        card,
                        settings,
                        referral.code,
                    )
                ],
                cache_time=30,
                is_personal=True,
            )
            return

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
