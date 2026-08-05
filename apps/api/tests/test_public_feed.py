import io
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.config import get_settings
from app.models import NotificationOutbox, User
from app.notification_worker import claim_due, deliver_one
from app.public_feed import (
    KIND_PUBLIC_FEED,
    PublicFeedFacts,
    enqueue_public_feed,
    public_actor_name,
    public_feed_caption,
    render_public_feed_card,
)


def test_public_feed_cards_render_all_confirmed_event_kinds() -> None:
    for event_kind in ("bank_entry", "bank_payout", "duel_entry", "duel_payout"):
        content = render_public_feed_card(
            PublicFeedFacts(
                event_id=f"event-{event_kind}",
                event_kind=event_kind,
                amount_nano=2_500_000_000,
                result_nano=1_500_000_000,
                queue_position=7,
                actor="@loop_user",
            )
        )
        image = Image.open(io.BytesIO(content))
        assert image.format == "JPEG"
        assert image.size == (1080, 1080)
        assert len(content) < 5_000_000


def test_public_feed_never_exposes_private_profile_name() -> None:
    public = User(telegram_id=910_001, username="visible", first_name="Private Name")
    private = User(telegram_id=910_002, first_name="Private Name")
    assert public_actor_name(public) == "@visible"
    assert public_actor_name(private) == "Участник LOOP"
    caption = public_feed_caption(
        PublicFeedFacts(
            event_id="privacy",
            event_kind="bank_entry",
            amount_nano=1_000_000_000,
            queue_position=3,
            actor=public_actor_name(private),
        )
    )
    assert "Private Name" not in caption
    assert "910002" not in caption


@pytest.mark.asyncio
async def test_public_feed_is_configurable_and_deduplicated(app) -> None:
    disabled = get_settings().model_copy(update={"public_feed_chat_id": 0})
    enabled = get_settings().model_copy(update={"public_feed_chat_id": -1003933253277})
    async with app.state.session_factory() as db:
        user = User(telegram_id=910_003, username="alice", first_name="Alice")
        db.add(user)
        await db.flush()
        skipped = await enqueue_public_feed(
            db,
            disabled,
            user_id=user.id,
            event_kind="bank_entry",
            event_key="bank-entry-disabled",
            amount_nano=1_000_000_000,
            queue_position=4,
            network=-3,
            tx_hash="aa" * 32,
        )
        assert skipped is None
        first = await enqueue_public_feed(
            db,
            enabled,
            user_id=user.id,
            event_kind="bank_entry",
            event_key="bank-entry-one",
            amount_nano=1_000_000_000,
            queue_position=4,
            network=-3,
            tx_hash="bb" * 32,
        )
        repeated = await enqueue_public_feed(
            db,
            enabled,
            user_id=user.id,
            event_kind="bank_entry",
            event_key="bank-entry-one",
            amount_nano=1_000_000_000,
            queue_position=4,
            network=-3,
            tx_hash="bb" * 32,
        )
        await db.commit()
        assert first is not None
        assert repeated is first
        assert (
            await db.scalar(
                select(func.count())
                .select_from(NotificationOutbox)
                .where(NotificationOutbox.kind == KIND_PUBLIC_FEED)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_public_feed_delivery_is_rich_and_ignores_private_notification_toggle(app) -> None:
    settings = get_settings().model_copy(
        update={
            "public_feed_chat_id": -1003933253277,
            "bot_username": "getloopbot",
        }
    )
    async with app.state.session_factory() as db:
        user = User(
            telegram_id=910_004,
            username="duelist",
            first_name="Duelist",
            result_notifications_enabled=False,
        )
        db.add(user)
        await db.flush()
        item = await enqueue_public_feed(
            db,
            settings,
            user_id=user.id,
            event_kind="duel_payout",
            event_key="duel-payout-one",
            amount_nano=2_500_000_000,
            result_nano=1_500_000_000,
            network=-3,
            tx_hash="cc" * 32,
        )
        assert item is not None
        item_id = item.id
        await db.commit()

    class FakeBot:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def send_photo(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(message_id=501)

    bot = FakeBot()
    claimed = await claim_due(app.state.session_factory)
    assert claimed == [item_id]
    await deliver_one(bot, app.state.session_factory, settings, item_id)  # type: ignore[arg-type]
    assert len(bot.calls) == 1
    call = bot.calls[0]
    assert call["chat_id"] == -1003933253277
    assert call["parse_mode"] == "HTML"
    assert call["show_caption_above_media"] is True
    assert "@duelist" in call["caption"]
    assert "+1,5 GRAM" in call["caption"]
    assert call["photo"].endswith(f"/{item_id}.jpg?v=1")
    buttons = call["reply_markup"].inline_keyboard[0]
    assert buttons[0].url == "https://t.me/getloopbot?startapp=duel"
    assert "transaction" in buttons[1].url

    async with app.state.session_factory() as db:
        delivered = await db.get(NotificationOutbox, item_id)
        assert delivered is not None
        assert delivered.state == "sent"
        assert delivered.telegram_message_id == 501


@pytest.mark.asyncio
async def test_public_feed_card_route_serves_only_public_outbox(client, app) -> None:
    settings = get_settings().model_copy(update={"public_feed_chat_id": -1003933253277})
    async with app.state.session_factory() as db:
        user = User(telegram_id=910_005, username="viewer", first_name="Viewer")
        db.add(user)
        await db.flush()
        item = await enqueue_public_feed(
            db,
            settings,
            user_id=user.id,
            event_kind="duel_entry",
            event_key="duel-entry-route",
            amount_nano=750_000_000,
            network=-3,
            tx_hash="dd" * 32,
        )
        assert item is not None
        item_id = item.id
        await db.commit()

    response = await client.get(f"/api/v1/public-feed/cards/{item_id}.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(response.content)).size == (1080, 1080)
    missing = await client.get("/api/v1/public-feed/cards/not-an-id.jpg")
    assert missing.status_code == 404
