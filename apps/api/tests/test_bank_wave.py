from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
from app.models import User
from app.modules.bank.models import BankPosition, BankPositionStatus
from app.modules.bank.wave import bank_wave_view, wave_window

WAVE_START = datetime(2026, 8, 16, 17, 0, tzinfo=UTC)
PROJECT_WALLET = "0:" + "99" * 32


def wave_settings():
    return get_settings().model_copy(
        update={
            "bank_wave_enabled": True,
            "bank_wave_wallet": PROJECT_WALLET,
            "bank_wave_goal": 8,
            "bank_wave_boost_nano": 5_000_000_000,
            "bank_wave_campaign_starts_at": WAVE_START,
            "bank_wave_max_boosts": 4,
        }
    )


def entry(*, position_id: int, user_id: str | None, wallet: str, confirmed_at: datetime):
    settings = wave_settings()
    return BankPosition(
        position_id=position_id,
        user_id=user_id,
        owner_wallet=wallet,
        network=settings.ton_network_id,
        contract_address=settings.bank_contract_address,
        query_id=900_000 + position_id,
        principal_nano=5_000_000_000 if wallet == PROJECT_WALLET else 1_000_000_000,
        multiplier_bps=12_500,
        target_payout_nano=6_250_000_000,
        funded_amount_nano=0,
        remaining_amount_nano=6_250_000_000,
        queue_index=position_id,
        current_status=BankPositionStatus.QUEUED.value,
        funding_transaction=f"wave-{position_id}",
        confirmed_at=confirmed_at,
    )


def test_wave_window_uses_sunday_moscow_time_and_keeps_result_for_a_day() -> None:
    settings = wave_settings()
    upcoming, upcoming_end = wave_window(datetime(2026, 8, 12, 12, tzinfo=UTC), settings)
    assert upcoming == WAVE_START
    assert upcoming_end == WAVE_START + timedelta(minutes=30)

    recent, _ = wave_window(WAVE_START + timedelta(hours=2), settings)
    assert recent == WAVE_START


@pytest.mark.asyncio
async def test_wave_counts_distinct_people_and_never_counts_the_loop_wallet(app) -> None:
    settings = wave_settings()
    async with app.state.session_factory() as db:
        first = User(telegram_id=800_001, first_name="One")
        second = User(telegram_id=800_002, first_name="Two")
        db.add_all([first, second])
        await db.flush()
        db.add_all(
            [
                entry(
                    position_id=801,
                    user_id=first.id,
                    wallet="0:" + "01" * 32,
                    confirmed_at=WAVE_START + timedelta(minutes=1),
                ),
                # A second position from one person is still one participant.
                entry(
                    position_id=802,
                    user_id=first.id,
                    wallet="0:" + "02" * 32,
                    confirmed_at=WAVE_START + timedelta(minutes=2),
                ),
                entry(
                    position_id=803,
                    user_id=second.id,
                    wallet="0:" + "03" * 32,
                    confirmed_at=WAVE_START + timedelta(minutes=3),
                ),
                entry(
                    position_id=804,
                    user_id=None,
                    wallet=PROJECT_WALLET,
                    confirmed_at=WAVE_START + timedelta(minutes=4),
                ),
            ]
        )
        await db.commit()

        wave = await bank_wave_view(
            db,
            settings,
            user_id=first.id,
            now=WAVE_START + timedelta(minutes=10),
        )

    assert wave is not None
    assert wave.state == "active"
    assert wave.participants == 2
    assert not wave.is_closer


@pytest.mark.asyncio
async def test_completed_wave_names_the_last_distinct_person_and_links_the_boost(app) -> None:
    settings = wave_settings()
    async with app.state.session_factory() as db:
        users = [
            User(telegram_id=810_000 + index, first_name=f"Wave {index}") for index in range(8)
        ]
        db.add_all(users)
        await db.flush()
        for index, user in enumerate(users):
            db.add(
                entry(
                    position_id=820 + index,
                    user_id=user.id,
                    wallet=f"0:{index + 10:064x}",
                    confirmed_at=WAVE_START + timedelta(minutes=index + 1),
                )
            )
        boost = entry(
            position_id=899,
            user_id=None,
            wallet=PROJECT_WALLET,
            confirmed_at=WAVE_START + timedelta(minutes=35),
        )
        boost.funding_transaction = "boost-proof"
        db.add(boost)
        await db.commit()

        wave = await bank_wave_view(
            db,
            settings,
            user_id=users[-1].id,
            now=WAVE_START + timedelta(hours=1),
        )

    assert wave is not None
    assert wave.state == "completed"
    assert wave.participants == 8
    assert wave.closer_name == "Wave 7"
    assert wave.is_closer
    assert wave.boost_confirmed
    assert wave.proof_url and "boost-proof" in wave.proof_url


@pytest.mark.asyncio
async def test_campaign_stops_advertising_after_four_verified_boosts(app) -> None:
    settings = wave_settings()
    async with app.state.session_factory() as db:
        for index in range(4):
            boost = entry(
                position_id=910 + index,
                user_id=None,
                wallet=PROJECT_WALLET,
                confirmed_at=WAVE_START + timedelta(weeks=index, minutes=35),
            )
            boost.funding_transaction = f"season-boost-{index}"
            db.add(boost)
        await db.commit()

        wave = await bank_wave_view(
            db,
            settings,
            now=WAVE_START + timedelta(weeks=4, days=-3),
        )

    assert wave is None
