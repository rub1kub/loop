import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.bank_momentum_notifications import (
    KIND_BANK_MOMENTUM,
    bank_momentum_text,
    enqueue_bank_momentum,
    enqueue_payout_ready_notifications,
    enqueue_teammate_entry_notifications,
)
from app.config import get_settings
from app.models import NotificationOutbox, User
from app.modules.bank.models import BankPosition, BankPositionStatus
from app.modules.teams.models import Team, TeamMembership, TeamScoreEvent, TeamSeason
from app.notification_worker import claim_due, deliver_one


@pytest.mark.asyncio
async def test_momentum_obeys_opt_in_dedupe_and_one_per_moscow_day(app) -> None:
    now = datetime(2026, 8, 16, 17, 20, tzinfo=UTC)
    async with app.state.session_factory() as db:
        enabled = User(telegram_id=850_001, first_name="Enabled")
        disabled = User(
            telegram_id=850_002,
            first_name="Disabled",
            result_notifications_enabled=False,
        )
        db.add_all([enabled, disabled])
        await db.flush()

        assert (
            await enqueue_bank_momentum(
                db,
                user_ids=[enabled.id, disabled.id],
                event_key="first",
                payload={"event": "wave_near", "remaining": 2},
                now=now,
            )
            == 1
        )
        await db.flush()
        assert (
            await enqueue_bank_momentum(
                db,
                user_ids=[enabled.id],
                event_key="second",
                payload={"event": "payout_ready", "positions": 1},
                now=now + timedelta(hours=1),
            )
            == 0
        )
        await db.commit()

    async with app.state.session_factory() as db:
        rows = (
            await db.scalars(
                select(NotificationOutbox).where(NotificationOutbox.kind == KIND_BANK_MOMENTUM)
            )
        ).all()
    assert len(rows) == 1
    assert json.loads(rows[0].payload_json)["remaining"] == 2


@pytest.mark.asyncio
async def test_teammate_signal_excludes_the_entrant_and_people_who_left(app) -> None:
    now = datetime(2026, 8, 16, 17, 10, tzinfo=UTC)
    settings = get_settings()
    async with app.state.session_factory() as db:
        entrant = User(telegram_id=851_001, first_name="Ира")
        teammate = User(telegram_id=851_002, first_name="Друг")
        former = User(telegram_id=851_003, first_name="Бывший")
        db.add_all([entrant, teammate, former])
        await db.flush()
        team = Team(
            slug="momentum",
            name="Momentum",
            description="",
            tag="MOM",
            mark=0,
            owner_user_id=entrant.id,
        )
        season = TeamSeason(
            season_key="2026-08-10",
            name="10–16 АВГУСТА",
            starts_at=datetime(2026, 8, 9, 21, tzinfo=UTC),
            ends_at=datetime(2026, 8, 16, 21, tzinfo=UTC),
        )
        db.add_all([team, season])
        await db.flush()
        memberships = [
            TeamMembership(team_id=team.id, user_id=entrant.id, role="owner"),
            TeamMembership(team_id=team.id, user_id=teammate.id, role="member"),
            TeamMembership(
                team_id=team.id,
                user_id=former.id,
                role="member",
                state="left",
                left_at=now,
            ),
        ]
        db.add_all(memberships)
        await db.flush()
        position = BankPosition(
            position_id=851,
            query_id=851,
            user_id=entrant.id,
            owner_wallet="0:" + "51" * 32,
            network=settings.ton_network_id,
            contract_address=settings.bank_contract_address,
            principal_nano=1_000_000_000,
            multiplier_bps=12_500,
            target_payout_nano=1_250_000_000,
            remaining_amount_nano=1_250_000_000,
            current_status=BankPositionStatus.QUEUED.value,
            confirmed_at=now,
        )
        db.add(position)
        await db.flush()
        db.add(
            TeamScoreEvent(
                season_id=season.id,
                team_id=team.id,
                membership_id=memberships[0].id,
                user_id=entrant.id,
                source_kind="bank_entry",
                source_entity_id=position.id,
                source_key=f"bank_entry:{position.network}:{position.id}",
                amount_nano=position.principal_nano,
                network=position.network,
                tx_hash="aa" * 32,
                event_at=now,
            )
        )
        await db.flush()
        assert await enqueue_teammate_entry_notifications(db, position=position, now=now) == 1
        await db.commit()

    async with app.state.session_factory() as db:
        recipients = set(
            await db.scalars(
                select(NotificationOutbox.user_id).where(
                    NotificationOutbox.kind == KIND_BANK_MOMENTUM
                )
            )
        )
    assert recipients == {teammate.id}


@pytest.mark.asyncio
async def test_a_delayed_chain_replay_does_not_send_stale_team_news(app) -> None:
    confirmed_at = datetime(2026, 8, 16, 17, 10, tzinfo=UTC)
    position = SimpleNamespace(
        id="stale-position",
        user_id="stale-user",
        network=-239,
        confirmed_at=confirmed_at,
    )
    async with app.state.session_factory() as db:
        assert (
            await enqueue_teammate_entry_notifications(
                db,
                position=position,
                now=confirmed_at + timedelta(minutes=31),
            )
            == 0
        )


@pytest.mark.asyncio
async def test_payout_ready_returns_only_confirmed_former_bank_users(app) -> None:
    now = datetime(2026, 8, 16, 17, 15, tzinfo=UTC)
    settings = get_settings()
    async with app.state.session_factory() as db:
        head_owner = User(telegram_id=851_101, first_name="Head")
        former = User(telegram_id=851_102, first_name="Former")
        newcomer = User(telegram_id=851_103, first_name="New")
        db.add_all([head_owner, former, newcomer])
        await db.flush()
        head = BankPosition(
            position_id=861,
            query_id=861,
            user_id=head_owner.id,
            owner_wallet="0:" + "61" * 32,
            network=settings.ton_network_id,
            contract_address=settings.bank_contract_address,
            principal_nano=1_000_000_000,
            multiplier_bps=12_500,
            target_payout_nano=1_250_000_000,
            funded_amount_nano=350_000_000,
            remaining_amount_nano=900_000_000,
            queue_index=0,
            current_status=BankPositionStatus.PARTIALLY_FUNDED.value,
            confirmed_at=now - timedelta(days=2),
        )
        old = BankPosition(
            position_id=862,
            query_id=862,
            user_id=former.id,
            owner_wallet="0:" + "62" * 32,
            network=settings.ton_network_id,
            contract_address=settings.bank_contract_address,
            principal_nano=1_000_000_000,
            multiplier_bps=12_500,
            target_payout_nano=1_250_000_000,
            funded_amount_nano=1_250_000_000,
            remaining_amount_nano=0,
            queue_index=1,
            current_status=BankPositionStatus.PAYOUT_SENT.value,
            funding_transaction="old-entry",
            payout_transaction="old-payout",
            confirmed_at=now - timedelta(days=7),
            completed_at=now - timedelta(days=6),
        )
        db.add_all([head, old])
        await db.flush()

        assert (
            await enqueue_payout_ready_notifications(
                db,
                settings,
                exclude_user_id=None,
                now=now,
            )
            == 1
        )
        await db.commit()

    async with app.state.session_factory() as db:
        recipients = set(
            await db.scalars(
                select(NotificationOutbox.user_id).where(
                    NotificationOutbox.kind == KIND_BANK_MOMENTUM
                )
            )
        )
    assert recipients == {former.id}


def test_momentum_copy_is_short_and_literal() -> None:
    assert "Осталось 2 человека" in bank_momentum_text(
        {"event": "wave_near", "remaining": 2}
    )
    assert "Ира сейчас в BANK" in bank_momentum_text(
        {"event": "teammate_joined", "name": "Ира"}
    )
    assert "<script>" not in bank_momentum_text(
        {"event": "teammate_joined", "name": "<script>"}
    )
    assert "Следующий вход закроет" in bank_momentum_text(
        {"event": "payout_ready", "positions": 1}
    )


@pytest.mark.asyncio
async def test_momentum_delivery_opens_bank(app) -> None:
    async with app.state.session_factory() as db:
        user = User(telegram_id=852_001, first_name="Momentum")
        db.add(user)
        await db.flush()
        db.add(
            NotificationOutbox(
                user_id=user.id,
                kind=KIND_BANK_MOMENTUM,
                dedupe_key="bank_momentum:delivery",
                payload_json=json.dumps({"event": "payout_ready", "positions": 1}),
                next_attempt_at=datetime.now(UTC),
            )
        )
        await db.commit()

    class FakeBot:
        def __init__(self) -> None:
            self.messages: list[dict] = []

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)
            return SimpleNamespace(message_id=852)

    bot = FakeBot()
    claimed = await claim_due(app.state.session_factory)
    await deliver_one(bot, app.state.session_factory, get_settings(), claimed[0])  # type: ignore[arg-type]
    assert bot.messages[0]["reply_markup"].inline_keyboard[0][0].text == "ОТКРЫТЬ BANK"
