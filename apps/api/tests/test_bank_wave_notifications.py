import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import NotificationOutbox, User
from app.notification_worker import claim_due, deliver_one, process_once


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=701)


def settings():
    return get_settings().model_copy(
        update={
            "bank_wave_enabled": True,
            "bank_wave_wallet": "0:" + "99" * 32,
            "bank_wave_goal": 8,
            "bank_wave_boost_nano": 5_000_000_000,
        }
    )


@pytest.mark.asyncio
async def test_notifier_never_materialises_weekly_event_notifications(app) -> None:
    async with app.state.session_factory() as db:
        db.add(User(telegram_id=830_001, first_name="Enabled"))
        await db.commit()

    bot = FakeBot()
    await process_once(bot, app.state.session_factory, settings())  # type: ignore[arg-type]

    async with app.state.session_factory() as db:
        rows = (
            await db.scalars(
                select(NotificationOutbox).where(NotificationOutbox.kind == "bank_wave")
            )
        ).all()
    assert rows == []
    assert bot.messages == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "payload"),
    [
        ("bank_wave", {"event": "start"}),
        ("bank_wave", {"event": "closed"}),
        ("bank_wave", {"event": "closer"}),
        ("bank_momentum", {"event": "wave_near", "remaining": 2}),
    ],
)
async def test_legacy_event_notification_is_blocked_without_delivery(
    app, kind: str, payload: dict[str, object]
) -> None:
    async with app.state.session_factory() as db:
        user = User(telegram_id=830_002, first_name="Legacy")
        db.add(user)
        await db.flush()
        notice = NotificationOutbox(
            user_id=user.id,
            kind=kind,
            dedupe_key=f"retired:{kind}:{payload['event']}",
            payload_json=json.dumps(payload),
            next_attempt_at=datetime.now(UTC),
        )
        db.add(notice)
        await db.commit()
        notice_id = notice.id

    bot = FakeBot()
    claimed = await claim_due(app.state.session_factory)
    assert claimed == [notice_id]
    await deliver_one(bot, app.state.session_factory, get_settings(), notice_id)  # type: ignore[arg-type]

    async with app.state.session_factory() as db:
        notice = await db.get(NotificationOutbox, notice_id)
        assert notice is not None
        assert notice.state == "blocked"
        assert notice.last_error == "event_notifications_retired"
    assert bot.messages == []


@pytest.mark.asyncio
async def test_unrelated_bank_momentum_notification_still_delivers(app) -> None:
    async with app.state.session_factory() as db:
        user = User(telegram_id=830_003, first_name="Member")
        db.add(user)
        await db.flush()
        notice = NotificationOutbox(
            user_id=user.id,
            kind="bank_momentum",
            dedupe_key="bank_momentum:still-supported",
            payload_json=json.dumps({"event": "teammate_joined", "name": "Друг"}),
            next_attempt_at=datetime.now(UTC),
        )
        db.add(notice)
        await db.commit()
        notice_id = notice.id

    bot = FakeBot()
    claimed = await claim_due(app.state.session_factory)
    assert claimed == [notice_id]
    await deliver_one(bot, app.state.session_factory, get_settings(), notice_id)  # type: ignore[arg-type]

    assert len(bot.messages) == 1
    assert "Друг сейчас в BANK" in bot.messages[0]["text"]
