import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.duel_notifications import match_notification_text
from app.models import NotificationOutbox, User
from app.modules.duel.models import Duel, DuelState, MatchmakingOffer, OfferState
from app.notification_worker import claim_due, deliver_one


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.photos: list[dict] = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=501)

    async def send_photo(self, **kwargs):
        self.photos.append(kwargs)
        return SimpleNamespace(message_id=502)


async def matched_duel(app, *, telegram_id: int, state: str, reveal_in: int):
    now = datetime.now(UTC).replace(microsecond=0)
    async with app.state.session_factory() as db:
        user = User(telegram_id=telegram_id, first_name="Matched")
        db.add(user)
        await db.flush()
        offers = []
        for index in range(2):
            offer = MatchmakingOffer(
                user_id=user.id if index == 0 else None,
                network=-3,
                onchain_offer_id=telegram_id * 10 + index,
                query_id=telegram_id * 10 + index,
                contract_address=get_settings().effective_duel_contract_address,
                owner_wallet=f"0:{index}{'0' * 62}",
                chance_bps=5_000,
                stake_nano=1_000_000_000,
                opponent_stake_nano=1_000_000_000,
                total_pool_nano=2_000_000_000,
                fee_bps=250,
                payout_nano=1_950_000_000,
                commitment_hex="ab" * 32,
                mode="afk",
                state=OfferState.MATCHED.value,
                expires_at=now + timedelta(minutes=15),
            )
            db.add(offer)
            offers.append(offer)
        await db.flush()
        duel = Duel(
            onchain_duel_id=telegram_id,
            network=-3,
            offer_a_id=offers[0].id,
            offer_b_id=offers[1].id,
            state=state,
            boost_deadline=now + timedelta(seconds=60),
            hard_deadline=now + timedelta(seconds=180),
            reveal_deadline=now + timedelta(seconds=reveal_in),
            boost_revision=0,
        )
        db.add(duel)
        await db.flush()
        db.add(
            NotificationOutbox(
                user_id=user.id,
                kind="duel_matched",
                dedupe_key=f"duel_matched:{duel.id}:{user.id}",
                payload_json=json.dumps(
                    {
                        "duel_id": duel.id,
                        "onchain_duel_id": duel.onchain_duel_id,
                        "network": -3,
                        "offer_id": offers[0].onchain_offer_id,
                        "stake_nano": 1_000_000_000,
                        "chance_bps": 5_000,
                        "boost_deadline": duel.boost_deadline.isoformat(),
                        "reveal_deadline": duel.reveal_deadline.isoformat(),
                    }
                ),
                result_card_id=None,
            )
        )
        await db.commit()
        return user.id


@pytest.mark.asyncio
async def test_match_alert_reaches_a_player_who_left(app) -> None:
    settings = get_settings()
    await matched_duel(app, telegram_id=910_001, state=DuelState.BOOSTING.value, reveal_in=360)

    bot = FakeBot()
    claimed = await claim_due(app.state.session_factory)
    assert len(claimed) == 1
    await deliver_one(bot, app.state.session_factory, settings, claimed[0])  # type: ignore[arg-type]

    assert len(bot.messages) == 1
    assert bot.photos == []
    text = bot.messages[0]["text"]
    assert "Соперник найден" in text
    assert "он заберёт весь пул" in text
    async with app.state.session_factory() as db:
        row = await db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.kind == "duel_matched")
        )
        assert row is not None
        assert row.state == "sent"
        assert row.telegram_message_id == 501


@pytest.mark.asyncio
async def test_match_alert_is_dropped_once_the_duel_is_over(app) -> None:
    settings = get_settings()
    await matched_duel(app, telegram_id=910_002, state=DuelState.SETTLED.value, reveal_in=360)

    bot = FakeBot()
    claimed = await claim_due(app.state.session_factory)
    await deliver_one(bot, app.state.session_factory, settings, claimed[0])  # type: ignore[arg-type]

    assert bot.messages == []
    async with app.state.session_factory() as db:
        row = await db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.kind == "duel_matched")
        )
        assert row is not None
        assert row.state == "blocked"
        assert row.last_error == "duel_closed"


@pytest.mark.asyncio
async def test_match_alert_is_dropped_once_nothing_can_be_done(app) -> None:
    settings = get_settings()
    await matched_duel(app, telegram_id=910_003, state=DuelState.REVEALING.value, reveal_in=-5)

    bot = FakeBot()
    claimed = await claim_due(app.state.session_factory)
    await deliver_one(bot, app.state.session_factory, settings, claimed[0])  # type: ignore[arg-type]

    assert bot.messages == []
    async with app.state.session_factory() as db:
        row = await db.scalar(
            select(NotificationOutbox).where(NotificationOutbox.kind == "duel_matched")
        )
        assert row is not None
        assert row.state == "blocked"
        assert row.last_error == "deadline_passed"


@pytest.mark.asyncio
async def test_match_alert_ignores_the_share_card_preference(app) -> None:
    settings = get_settings()
    user_id = await matched_duel(
        app, telegram_id=910_004, state=DuelState.BOOSTING.value, reveal_in=360
    )
    async with app.state.session_factory() as db:
        user = await db.get(User, user_id)
        assert user is not None
        user.result_notifications_enabled = False
        await db.commit()

    bot = FakeBot()
    claimed = await claim_due(app.state.session_factory)
    await deliver_one(bot, app.state.session_factory, settings, claimed[0])  # type: ignore[arg-type]

    assert len(bot.messages) == 1


def test_match_text_never_names_an_action_that_may_be_unavailable() -> None:
    now = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
    payload = {"reveal_deadline": (now + timedelta(seconds=300)).isoformat()}
    text = match_notification_text(payload, now)

    assert "осталось 5 мин." in text
    assert "усиль" not in text.lower()
    assert "открой результат" not in text.lower()

    expiring = match_notification_text(
        {"reveal_deadline": (now + timedelta(seconds=30)).isoformat()}, now
    )
    assert "меньше минуты" in expiring
