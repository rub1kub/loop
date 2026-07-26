import hashlib
import hmac
import io
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from PIL import Image
from sqlalchemy import select

from app.config import get_settings
from app.models import NotificationOutbox, ReferralCode, ResultCard, User
from app.notification_worker import claim_due, deliver_one
from app.result_cards import CardFacts, create_result_card, render_result_card


def signed_init_data(telegram_id: int) -> str:
    values = {
        "auth_date": str(int(datetime.now(UTC).timestamp())),
        "query_id": f"AAE-results-{telegram_id}",
        "user": json.dumps(
            {"id": telegram_id, "first_name": f"User {telegram_id}"},
            separators=(",", ":"),
        ),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", b"123456:test-token", hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


async def authenticate(client, telegram_id: int) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": signed_init_data(telegram_id)},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def add_result(app, telegram_id: int, event_key: str = "bank:test") -> ResultCard:
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
        assert user is not None
        card = await create_result_card(
            db,
            user_id=user.id,
            mode="bank",
            entity_id="entity-result",
            event_key=event_key,
            network=-3,
            payout_nano=3_000_000_000,
            contributed_nano=2_000_000_000,
            tx_hash="ab" * 32,
        )
        assert card is not None
        await db.commit()
        await db.refresh(card)
        return card


def test_card_renderer_is_deterministic_and_telegram_sized() -> None:
    facts = CardFacts(
        public_id="sample_card_public_id_01",
        mode="duel",
        payout_nano=1_950_000_000,
        contributed_nano=1_000_000_000,
        result_nano=950_000_000,
    )
    first = render_result_card(facts)
    assert first == render_result_card(facts)
    assert first.startswith(b"\xff\xd8")
    assert len(first) < 5_000_000
    with Image.open(io.BytesIO(first)) as image:
        assert image.size == (1080, 1350)

    with pytest.raises(ValueError, match="positive"):
        render_result_card(
            CardFacts(
                public_id="invalid_card_public_id",
                mode="bank",
                payout_nano=1,
                contributed_nano=1,
                result_nano=0,
            )
        )


@pytest.mark.asyncio
async def test_result_api_is_owner_bound_but_card_image_is_public(client, app) -> None:
    owner_headers = await authenticate(client, 830_001)
    other_headers = await authenticate(client, 830_002)
    card = await add_result(app, 830_001)

    listed = await client.get("/api/v1/results", headers=owner_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [card.id]
    assert (await client.get("/api/v1/results", headers=other_headers)).json() == []

    image = await client.get(f"/api/v1/results/cards/{card.public_id}.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert image.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert image.content.startswith(b"\xff\xd8")
    assert (
        await client.get("/api/v1/results/cards/not-a-valid-public-id.jpg")
    ).status_code == 404

    forbidden = await client.post(
        f"/api/v1/results/{card.id}/prepare",
        headers=other_headers,
        json={},
    )
    assert forbidden.status_code == 404


@pytest.mark.asyncio
async def test_result_prepare_and_seen_use_native_telegram_share(client, app) -> None:
    headers = await authenticate(client, 830_003)
    card = await add_result(app, 830_003, "bank:prepare")

    class FakeBot:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.session = app.state.bot.session

        async def save_prepared_inline_message(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                id="prepared-result-message",
                expiration_date=datetime(2030, 1, 1, tzinfo=UTC),
            )

    bot = FakeBot()
    app.state.bot = bot
    prepared = await client.post(
        f"/api/v1/results/{card.id}/prepare",
        headers=headers,
        json={},
    )
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["prepared_message_id"] == "prepared-result-message"
    assert prepared.json()["fallback_query"] == f"result {card.public_id}"
    assert bot.calls[0]["allow_user_chats"] is True
    assert bot.calls[0]["allow_group_chats"] is True
    assert bot.calls[0]["result"].photo_url.endswith(f"/{card.public_id}.jpg")
    async with app.state.session_factory() as db:
        referral = await db.scalar(
            select(ReferralCode).where(ReferralCode.owner_user_id == card.user_id)
        )
        assert referral is not None
        share_buttons = bot.calls[0]["result"].reply_markup.inline_keyboard[0]
        assert share_buttons[0].url.endswith(f"?startapp=ref_{referral.code}")

    seen = await client.post(f"/api/v1/results/{card.id}/seen", headers=headers, json={})
    assert seen.status_code == 200
    assert seen.json()["seen_at"] is not None
    repeated = await client.post(f"/api/v1/results/{card.id}/seen", headers=headers, json={})
    assert repeated.json()["seen_at"] == seen.json()["seen_at"]


@pytest.mark.asyncio
async def test_notification_outbox_sends_once_and_honours_user_setting(app) -> None:
    settings = get_settings()
    async with app.state.session_factory() as db:
        user = User(telegram_id=830_004, first_name="Notify")
        db.add(user)
        await db.flush()
        first = await create_result_card(
            db,
            user_id=user.id,
            mode="duel",
            entity_id="duel-one",
            event_key="duel:notify:one",
            network=-3,
            payout_nano=1_950_000_000,
            contributed_nano=1_000_000_000,
            tx_hash="cd" * 32,
        )
        assert first is not None
        await db.commit()

    class FakeBot:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def send_photo(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(message_id=77)

    bot = FakeBot()
    claimed = await claim_due(app.state.session_factory)
    assert len(claimed) == 1
    await deliver_one(bot, app.state.session_factory, settings, claimed[0])  # type: ignore[arg-type]
    assert len(bot.calls) == 1
    async with app.state.session_factory() as db:
        referral = await db.scalar(
            select(ReferralCode).where(ReferralCode.owner_user_id == user.id)
        )
        assert referral is not None
        notification_buttons = bot.calls[0]["reply_markup"].inline_keyboard[1]
        assert notification_buttons[0].url.endswith(f"?startapp=ref_{referral.code}")

    async with app.state.session_factory() as db:
        current_user = await db.get(User, user.id)
        assert current_user is not None
        outbox = await db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.result_card_id == first.id)
        )
        assert outbox is not None
        assert outbox.state == "sent"
        assert outbox.telegram_message_id == 77
        assert await create_result_card(
            db,
            user_id=user.id,
            mode="duel",
            entity_id="duel-one",
            event_key="duel:notify:one",
            network=-3,
            payout_nano=1_950_000_000,
            contributed_nano=1_000_000_000,
            tx_hash="cd" * 32,
        )
        current_user.result_notifications_enabled = False
        second = await create_result_card(
            db,
            user_id=user.id,
            mode="bank",
            entity_id="bank-two",
            event_key="bank:notify:two",
            network=-3,
            payout_nano=1_500_000_000,
            contributed_nano=1_000_000_000,
            tx_hash="ef" * 32,
        )
        assert second is not None
        await db.commit()

    second_claim = await claim_due(app.state.session_factory)
    assert len(second_claim) == 1
    await deliver_one(bot, app.state.session_factory, settings, second_claim[0])  # type: ignore[arg-type]
    assert len(bot.calls) == 1
    async with app.state.session_factory() as db:
        disabled = await db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.result_card_id == second.id)
        )
        assert disabled is not None and disabled.state == "blocked"
