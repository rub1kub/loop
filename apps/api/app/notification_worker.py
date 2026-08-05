import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import Message
from anyio import Path
from sqlalchemy import select, update

from .config import Settings, get_settings
from .database import create_database
from .duel_notifications import (
    KIND_DUEL_MATCHED,
    KIND_DUEL_REVEAL_SOON,
    KIND_REFERRAL_QUALIFIED,
    match_notification_markup,
    match_notification_text,
    referral_text,
    reveal_reminder_text,
)
from .models import NotificationOutbox, ResultCard, User
from .modules.duel.models import Duel, DuelState
from .public_feed import (
    KIND_PUBLIC_FEED,
    public_feed_caption,
    public_feed_card_url,
    public_feed_facts,
    public_feed_markup,
)
from .referrals import get_or_create_referral_code
from .result_cards import (
    notification_markup,
    result_caption,
    result_card_image_url,
)

logger = structlog.get_logger()
HEARTBEAT_FILE = Path("/tmp/loop-notifier-heartbeat")  # noqa: S108
MAX_BATCH = 20
MAX_ATTEMPTS = 8


async def fail_stale_claims(session_factory: Any) -> None:
    cutoff = datetime.now(UTC) - timedelta(minutes=10)
    async with session_factory() as db:
        await db.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.state == "processing",
                NotificationOutbox.updated_at < cutoff,
            )
            .values(
                state="failed",
                last_error="delivery_uncertain",
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()


async def claim_due(session_factory: Any) -> list[str]:
    now = datetime.now(UTC)
    async with session_factory() as db:
        await db.execute(
            update(NotificationOutbox)
            .where(
                NotificationOutbox.state == "retry",
                NotificationOutbox.attempts >= MAX_ATTEMPTS,
            )
            .values(state="failed", last_error="attempts_exhausted", updated_at=now)
        )
        rows = (
            await db.scalars(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.state.in_(["pending", "retry"]),
                    NotificationOutbox.next_attempt_at <= now,
                    NotificationOutbox.attempts < MAX_ATTEMPTS,
                )
                .order_by(NotificationOutbox.created_at)
                .limit(MAX_BATCH)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in rows:
            row.state = "processing"
            row.attempts += 1
            row.updated_at = now
        await db.commit()
        return [row.id for row in rows]


async def update_delivery(
    session_factory: Any,
    outbox_id: str,
    *,
    state: str,
    error: str | None = None,
    retry_after: int | None = None,
    message_id: int | None = None,
) -> None:
    now = datetime.now(UTC)
    values: dict[str, Any] = {
        "state": state,
        "last_error": error,
        "updated_at": now,
    }
    if retry_after is not None:
        values["next_attempt_at"] = now + timedelta(seconds=max(1, retry_after))
    if message_id is not None:
        values["telegram_message_id"] = message_id
        values["sent_at"] = now
    async with session_factory() as db:
        await db.execute(
            update(NotificationOutbox)
            .where(NotificationOutbox.id == outbox_id)
            .values(**values)
        )
        await db.commit()


async def send_with_effect(
    effect_id: str,
    send: Callable[[str | None], Awaitable[Message]],
) -> Message:
    """Sends with a message effect, and again without it if Telegram refuses.

    Telegram publishes no list of effect ids and the community ones disagree,
    so an id can be wrong. A decoration must never cost the notification.
    """
    if not effect_id:
        return await send(None)
    try:
        return await send(effect_id)
    except TelegramBadRequest:
        logger.warning("telegram rejected the message effect, sending without it")
        return await send(None)


async def deliver_plain_alert(
    bot: Bot,
    session_factory: Any,
    settings: Settings,
    outbox_id: str,
    kind: str,
    user: User | None,
    payload: dict[str, Any],
) -> None:
    """A confirmed friend, or the last call before a duel expires unplayed."""
    if user is None:
        await update_delivery(session_factory, outbox_id, state="failed", error="user_missing")
        return
    now = datetime.now(UTC)
    if kind == KIND_DUEL_REVEAL_SOON:
        deadline = datetime.fromisoformat(str(payload["reveal_deadline"]))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        # A warning that arrives after the window has closed is worse than none.
        if now >= deadline:
            await update_delivery(
                session_factory, outbox_id, state="blocked", error="deadline_passed"
            )
            return
        text = reveal_reminder_text(payload, now)
        effect = settings.match_effect_id.strip()
    else:
        text = referral_text(payload)
        effect = settings.referral_effect_id.strip()

    try:
        message = await send_with_effect(
            effect,
            lambda value: bot.send_message(
                chat_id=user.telegram_id,
                text=text,
                reply_markup=match_notification_markup(settings),
                message_effect_id=value,
            ),
        )
    except TelegramRetryAfter as exc:
        await update_delivery(
            session_factory,
            outbox_id,
            state="retry",
            error="telegram_rate_limit",
            retry_after=exc.retry_after,
        )
        return
    except TelegramForbiddenError:
        await update_delivery(session_factory, outbox_id, state="blocked", error="bot_blocked")
        return
    except TelegramAPIError as exc:
        await update_delivery(session_factory, outbox_id, state="retry", error=str(exc)[:180])
        return
    await update_delivery(
        session_factory, outbox_id, state="sent", message_id=message.message_id
    )


async def deliver_match_alert(
    bot: Bot,
    session_factory: Any,
    settings: Settings,
    outbox_id: str,
    user: User | None,
    duel: Duel | None,
    payload: dict[str, Any],
) -> None:
    if user is None or duel is None:
        await update_delivery(
            session_factory, outbox_id, state="failed", error="duel_or_user_missing"
        )
        return
    if duel.state not in {DuelState.BOOSTING.value, DuelState.REVEALING.value}:
        await update_delivery(session_factory, outbox_id, state="blocked", error="duel_closed")
        return
    now = datetime.now(UTC)
    deadline = duel.reveal_deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    if now >= deadline:
        await update_delivery(session_factory, outbox_id, state="blocked", error="deadline_passed")
        return

    try:
        message = await send_with_effect(
            settings.match_effect_id.strip(),
            lambda effect: bot.send_message(
                chat_id=user.telegram_id,
                text=match_notification_text(
                    {**payload, "reveal_deadline": deadline.isoformat()}, now
                ),
                reply_markup=match_notification_markup(settings),
                message_effect_id=effect,
            ),
        )
    except TelegramRetryAfter as exc:
        await update_delivery(
            session_factory,
            outbox_id,
            state="retry",
            error="telegram_rate_limit",
            retry_after=exc.retry_after,
        )
    except TelegramForbiddenError:
        await update_delivery(
            session_factory, outbox_id, state="blocked", error="telegram_forbidden"
        )
    except TelegramBadRequest:
        await update_delivery(
            session_factory, outbox_id, state="failed", error="telegram_bad_request"
        )
    except TelegramAPIError:
        await update_delivery(
            session_factory,
            outbox_id,
            state="retry",
            error="delivery_uncertain",
            retry_after=5,
        )
    else:
        await update_delivery(
            session_factory,
            outbox_id,
            state="sent",
            message_id=message.message_id,
        )


async def deliver_public_feed(
    bot: Bot,
    session_factory: Any,
    settings: Settings,
    outbox: NotificationOutbox,
    user: User | None,
) -> None:
    try:
        payload = json.loads(outbox.payload_json)
        facts = public_feed_facts(outbox, user)
        proof_url = str(payload["proof_url"])
        message = await bot.send_photo(
            chat_id=settings.public_feed_chat_id,
            photo=public_feed_card_url(settings, outbox.id),
            caption=public_feed_caption(facts),
            parse_mode="HTML",
            show_caption_above_media=True,
            reply_markup=public_feed_markup(settings, facts, proof_url),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        await update_delivery(
            session_factory, outbox.id, state="failed", error="public_payload_invalid"
        )
    except TelegramRetryAfter as exc:
        await update_delivery(
            session_factory,
            outbox.id,
            state="retry",
            error="telegram_rate_limit",
            retry_after=exc.retry_after,
        )
    except TelegramForbiddenError:
        await update_delivery(
            session_factory, outbox.id, state="blocked", error="telegram_forbidden"
        )
    except TelegramBadRequest:
        await update_delivery(
            session_factory, outbox.id, state="failed", error="telegram_bad_request"
        )
    except TelegramAPIError:
        # Telegram offers no sendPhoto idempotency key. An uncertain retry could
        # publish the same financial event twice and is therefore not attempted.
        await update_delivery(
            session_factory, outbox.id, state="failed", error="delivery_uncertain"
        )
    else:
        await update_delivery(
            session_factory,
            outbox.id,
            state="sent",
            message_id=message.message_id,
        )


async def deliver_one(
    bot: Bot,
    session_factory: Any,
    settings: Settings,
    outbox_id: str,
) -> None:
    async with session_factory() as db:
        outbox = await db.get(NotificationOutbox, outbox_id)
        if outbox is None or outbox.state != "processing":
            return
        kind = outbox.kind
        if kind == KIND_DUEL_MATCHED:
            payload = json.loads(outbox.payload_json)
            player = await db.get(User, outbox.user_id)
            duel = await db.get(Duel, payload["duel_id"])
        elif kind in (KIND_DUEL_REVEAL_SOON, KIND_REFERRAL_QUALIFIED):
            payload = json.loads(outbox.payload_json)
            plain_user = await db.get(User, outbox.user_id)
        elif kind == KIND_PUBLIC_FEED:
            public_outbox = outbox
            public_user = await db.get(User, outbox.user_id)
        else:
            payload = None
            card = await db.get(ResultCard, outbox.result_card_id)
            user = await db.get(User, outbox.user_id)
            referral = await get_or_create_referral_code(db, outbox.user_id) if user else None
    if kind == KIND_DUEL_MATCHED:
        await deliver_match_alert(bot, session_factory, settings, outbox_id, player, duel, payload)
        return
    if kind in (KIND_DUEL_REVEAL_SOON, KIND_REFERRAL_QUALIFIED):
        await deliver_plain_alert(
            bot, session_factory, settings, outbox_id, kind, plain_user, payload
        )
        return
    if kind == KIND_PUBLIC_FEED:
        await deliver_public_feed(
            bot, session_factory, settings, public_outbox, public_user
        )
        return
    if card is None or user is None:
        await update_delivery(
            session_factory, outbox_id, state="failed", error="result_or_user_missing"
        )
        return
    if not user.result_notifications_enabled:
        await update_delivery(
            session_factory, outbox_id, state="blocked", error="notifications_disabled"
        )
        return

    # A win is worth a little noise. Telegram publishes no list of effect ids
    # and the community ones disagree, so a rejected effect must never cost the
    # notification: the send is retried plainly.
    celebratory = card.mode != "bank_entry" and card.payout_nano > card.contributed_nano
    effect_id = settings.result_effect_id.strip() if celebratory else ""

    try:
        message = await send_with_effect(
            effect_id,
            lambda effect: bot.send_photo(
                chat_id=user.telegram_id,
                photo=result_card_image_url(settings, card),
                caption=result_caption(card),
                reply_markup=notification_markup(
                    card,
                    settings,
                    referral.code if referral else None,
                ),
                message_effect_id=effect,
            ),
        )
    except TelegramRetryAfter as exc:
        await update_delivery(
            session_factory,
            outbox_id,
            state="retry",
            error="telegram_rate_limit",
            retry_after=exc.retry_after,
        )
    except TelegramForbiddenError:
        async with session_factory() as db:
            current_user = await db.get(User, user.id)
            if current_user:
                current_user.result_notifications_enabled = False
            await db.commit()
        await update_delivery(
            session_factory, outbox_id, state="blocked", error="telegram_forbidden"
        )
    except TelegramBadRequest:
        await update_delivery(
            session_factory, outbox_id, state="failed", error="telegram_bad_request"
        )
    except TelegramAPIError:
        # Telegram has no idempotency key for sendPhoto. An ambiguous transport
        # failure is not retried, otherwise a successful first request could
        # produce a duplicate card. The result remains available in the app.
        await update_delivery(
            session_factory, outbox_id, state="failed", error="delivery_uncertain"
        )
    else:
        await update_delivery(
            session_factory,
            outbox_id,
            state="sent",
            message_id=message.message_id,
        )


async def process_once(
    bot: Bot,
    session_factory: Any,
    settings: Settings,
) -> int:
    await fail_stale_claims(session_factory)
    outbox_ids = await claim_due(session_factory)
    for outbox_id in outbox_ids:
        await deliver_one(bot, session_factory, settings, outbox_id)
    await HEARTBEAT_FILE.touch()
    return len(outbox_ids)


async def main() -> None:
    settings = get_settings()
    token = settings.bot_token.get_secret_value()
    if not token:
        raise RuntimeError("LOOP_BOT_TOKEN is required for notification delivery")
    engine, session_factory = create_database(settings)
    bot = Bot(token)
    try:
        while True:
            try:
                await process_once(bot, session_factory, settings)
            except Exception as exc:
                logger.exception("notification_worker_iteration_failed", error=type(exc).__name__)
            await asyncio.sleep(5)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
