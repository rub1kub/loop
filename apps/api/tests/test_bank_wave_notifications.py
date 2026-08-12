import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.bank_wave_notifications import bank_wave_text, ensure_bank_wave_notifications
from app.config import get_settings
from app.models import NotificationOutbox, User
from app.modules.bank.models import BankPosition, BankPositionStatus
from app.notification_worker import claim_due, deliver_one


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
async def test_wave_opening_is_scheduled_once_and_respects_the_user_toggle(app) -> None:
    async with app.state.session_factory() as db:
        enabled = User(telegram_id=830_001, first_name="Enabled")
        disabled = User(
            telegram_id=830_002,
            first_name="Disabled",
            result_notifications_enabled=False,
        )
        db.add_all([enabled, disabled])
        await db.commit()

    now = datetime(2026, 8, 12, 12, tzinfo=UTC)
    assert await ensure_bank_wave_notifications(app.state.session_factory, settings(), now=now) == 1
    assert await ensure_bank_wave_notifications(app.state.session_factory, settings(), now=now) == 0

    async with app.state.session_factory() as db:
        rows = (
            await db.scalars(
                select(NotificationOutbox).where(NotificationOutbox.kind == "bank_wave")
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].user_id == enabled.id
    assert json.loads(rows[0].payload_json)["event"] == "start"
    scheduled = rows[0].next_attempt_at
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=UTC)
    assert scheduled > now


def test_wave_messages_are_short_and_do_not_promise_a_cash_prize() -> None:
    opening = bank_wave_text({"event": "start"})
    closer = bank_wave_text({"event": "closer"})
    assert "5 GRAM в BANK" in opening
    assert "Ты закрыл Волну" in closer
    assert "приз" not in (opening + closer).lower()


@pytest.mark.asyncio
async def test_wave_near_signal_appears_at_two_people_remaining(app) -> None:
    config = settings()
    now = datetime(2026, 8, 16, 17, 10, tzinfo=UTC)
    async with app.state.session_factory() as db:
        users = [User(telegram_id=835_000 + index, first_name=str(index)) for index in range(6)]
        db.add_all(users)
        await db.flush()
        for index, user in enumerate(users):
            db.add(
                BankPosition(
                    position_id=835 + index,
                    query_id=835 + index,
                    user_id=user.id,
                    owner_wallet=f"0:{index + 1:064x}",
                    network=config.ton_network_id,
                    contract_address=config.bank_contract_address,
                    principal_nano=1_000_000_000,
                    multiplier_bps=12_500,
                    target_payout_nano=1_250_000_000,
                    remaining_amount_nano=1_250_000_000,
                    queue_index=index,
                    current_status=BankPositionStatus.QUEUED.value,
                    funding_transaction=f"wave-near-{index}",
                    confirmed_at=now - timedelta(minutes=6 - index),
                )
            )
        await db.commit()

    await ensure_bank_wave_notifications(app.state.session_factory, config, now=now)
    async with app.state.session_factory() as db:
        notices = (
            await db.scalars(
                select(NotificationOutbox).where(NotificationOutbox.kind == "bank_momentum")
            )
        ).all()
    assert len(notices) == 6
    assert all(json.loads(item.payload_json)["remaining"] == 2 for item in notices)


@pytest.mark.asyncio
async def test_wave_message_opens_bank_instead_of_duel(app) -> None:
    async with app.state.session_factory() as db:
        user = User(telegram_id=830_003, first_name="Wave")
        db.add(user)
        await db.flush()
        db.add(
            NotificationOutbox(
                user_id=user.id,
                kind="bank_wave",
                dedupe_key="bank_wave:delivery",
                payload_json=json.dumps({"event": "start"}),
                next_attempt_at=datetime.now(UTC),
            )
        )
        await db.commit()

    bot = FakeBot()
    claimed = await claim_due(app.state.session_factory)
    await deliver_one(bot, app.state.session_factory, get_settings(), claimed[0])  # type: ignore[arg-type]

    assert len(bot.messages) == 1
    button = bot.messages[0]["reply_markup"].inline_keyboard[0][0]
    assert button.text == "ОТКРЫТЬ BANK"
    assert "startapp=bank" in button.url
