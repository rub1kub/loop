import asyncio
import re
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog
from aiogram import Bot, Dispatcher, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
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
from fastapi import HTTPException
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
from .modules.teams.card import build_team_invite_inline
from .modules.teams.models import Team
from .modules.teams.service import ensure_season, ranked_team_entry, resolve_invite
from .referrals import get_or_create_referral_code
from .result_cards import (
    INVITE_VARIANTS,
    build_invite_inline,
    build_result_inline,
    duel_opponent_label,
)

logger = structlog.get_logger()

INLINE_PATTERN = re.compile(r"^\s*duel\s+(\d{1,16})\s*$", re.IGNORECASE)
RESULT_PATTERN = re.compile(r"^\s*result\s+([A-Za-z0-9_-]{20,32})\s*$", re.IGNORECASE)
INVITE_PATTERN = re.compile(r"^\s*invite(\s+[A-Za-z0-9_-]{4,24})?\s*$", re.IGNORECASE)
TEAM_PATTERN = re.compile(r"^\s*team\s+([A-Za-z0-9_-]{12,48})\s*$", re.IGNORECASE)
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
    "∞ LOOP\n\nBANK — пирамида, DUEL — дуэль на бабки. Го, разберёшься на месте",
    "∞ LOOP\n\nТестим на реальных деньгах. BANK и DUEL уже внутри",
    "∞ LOOP\n\nОчередь BANK или дуэль DUEL — выбирай сам, го",
    "∞ LOOP\n\nBANK и DUEL, без прикрас. Заходи и смотри",
    "∞ LOOP\n\nBANK копит очередь, DUEL решает за минуту. Погнали",
    "∞ LOOP\n\nКод открыт, деньги настоящие. BANK и DUEL ждут внутри",
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
    rather than hand-duplicating every rotation entry as block literals — the
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

    @router.callback_query(lambda query: (query.data or "").startswith("bcast:"))
    async def broadcast_draft(query: CallbackQuery) -> None:
        """Send the draft above this button to everyone who can receive it.

        A draft arrives in the owner's chat first and is only ever a draft: the
        message is written, read, and then chosen. The button copies that exact
        message, so what people receive is what the owner approved — not a
        second rendering that could differ from it.

        Two guards, because one tap reaches four hundred people: only the
        configured owner chat may press it, and a message already sent cannot
        be sent twice.
        """
        presser = query.from_user.id if query.from_user else 0
        bot = query.bot
        if bot is None or not settings.alert_chat_id or presser != settings.alert_chat_id:
            await query.answer("Недоступно", show_alert=True)
            return
        source_id = (query.data or "").removeprefix("bcast:")
        if not source_id.isdigit():
            await query.answer("Нечего рассылать", show_alert=True)
            return
        guard = f"loop:broadcast-sent:{source_id}"
        if not await redis_client.set(guard, "1", ex=86_400, nx=True):
            await query.answer("Эта рассылка уже уходила", show_alert=True)
            return
        await query.answer("Рассылаю…")
        # Кнопка под рассылкой — не для владельца, а для получателя: один тап,
        # и человек пересылает новость дальше. Копия сообщения не наследует
        # разметку исходника, поэтому она задаётся здесь явно, и кнопка
        # владельца «разослать» на людей не попадает.
        # Кнопка отправляет не ссылку, а инлайн-приглашение: карточку строит
        # бот по тому, кто её нажал, и подставляет ЕГО реферальный код. Прежняя
        # ссылка вела на голый t.me/getloopbot — человек приводил людей и не
        # получал за них ничего, ровно на том действии, ради которого кнопка и
        # существует.
        share = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📤 ПОДЕЛИТЬСЯ", switch_inline_query="invite")]
            ]
        )
        async with session_factory() as db:
            targets = list(await db.scalars(select(User.telegram_id).order_by(User.created_at)))
        delivered = 0
        unreachable = 0
        for chat_id in targets:
            try:
                await bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=settings.alert_chat_id,
                    message_id=int(source_id),
                    reply_markup=share,
                )
                delivered += 1
            except TelegramRetryAfter as exc:
                await asyncio.sleep(exc.retry_after)
                unreachable += 1
            except TelegramAPIError:
                # Blocked, never started, deactivated — none of it should stop
                # the rest of the list.
                unreachable += 1
            await asyncio.sleep(0.06)
        await bot.send_message(
            settings.alert_chat_id,
            f"Разослано: {delivered}. Не доставлено: {unreachable} из {len(targets)}.",
        )

    @router.inline_query()
    async def inline_result_or_duel(query: InlineQuery) -> None:
        team_match = TEAM_PATTERN.match(query.query)
        if team_match:
            async with session_factory() as db:
                creator = await db.scalar(
                    select(User).where(User.telegram_id == query.from_user.id)
                )
                if creator is None:
                    await query.answer([], cache_time=1, is_personal=True)
                    return
                try:
                    invite = await resolve_invite(db, team_match.group(1))
                except HTTPException:
                    await query.answer([], cache_time=1, is_personal=True)
                    return
                team = await db.get(Team, invite.team_id)
                inviter = await db.get(User, invite.inviter_user_id)
                if team is None or inviter is None or team.state != "active":
                    await query.answer([], cache_time=1, is_personal=True)
                    return
                referral = await get_or_create_referral_code(db, inviter.id)
                season = await ensure_season(db)
                entry = await ranked_team_entry(
                    db, season, user_id=creator.id, team_id=team.id
                )
                if entry is None:
                    await query.answer([], cache_time=1, is_personal=True)
                    return
                await db.commit()
            await query.answer(
                [
                    build_team_invite_inline(
                        settings=settings,
                        team=entry,
                        token=team_match.group(1),
                        referral_code=referral.code,
                        inviter_name=inviter.first_name,
                    )
                ],
                cache_time=15,
                is_personal=True,
            )
            return

        invite_match = INVITE_PATTERN.match(query.query)
        if invite_match and settings.launch_at is not None:
            async with session_factory() as db:
                creator = await db.scalar(
                    select(User).where(User.telegram_id == query.from_user.id)
                )
                if creator is None:
                    await query.answer([], cache_time=1, is_personal=True)
                    return
                referral = await get_or_create_referral_code(db, creator.id)
            await query.answer(
                [
                    build_invite_inline(
                        settings=settings,
                        referral_code=referral.code,
                        first_name=creator.first_name,
                        username=creator.username,
                        launch_at=settings.launch_at,
                        variant_index=secrets.randbelow(len(INVITE_VARIANTS)),
                    )
                ],
                cache_time=30,
                is_personal=True,
            )
            return

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
                        await duel_opponent_label(db, card),
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
