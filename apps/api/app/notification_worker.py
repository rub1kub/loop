import asyncio
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
from anyio import Path
from sqlalchemy import select, update

from .config import Settings, get_settings
from .database import create_database
from .models import NotificationOutbox, ResultCard, User
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
        card = await db.get(ResultCard, outbox.result_card_id)
        user = await db.get(User, outbox.user_id)
        referral = await get_or_create_referral_code(db, outbox.user_id) if user else None
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

    try:
        message = await bot.send_photo(
            chat_id=user.telegram_id,
            photo=result_card_image_url(settings, card),
            caption=result_caption(card),
            reply_markup=notification_markup(
                card,
                settings,
                referral.code if referral else None,
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
