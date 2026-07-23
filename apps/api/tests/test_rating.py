from datetime import UTC, datetime, timedelta

import pytest

from app.models import ReferralAttribution, ReferralCode, User
from app.modules.bank.models import BankPayout, BankPosition, BankPositionStatus
from app.modules.duel.models import (
    Duel,
    DuelOffer,
    DuelPlayer,
    DuelReveal,
    DuelSettlement,
    DuelState,
    OfferState,
)
from app.rating import RatingMetrics, build_rating, level_for_score, score_metrics, season_window


def test_score_uses_verified_actions_and_timeout_behavior_only() -> None:
    metrics = RatingMetrics(
        bank_payouts=2,
        duel_settlements=3,
        timely_reveals=2,
        missed_reveals=1,
        qualified_referrals=1,
    )
    assert score_metrics(metrics) == 405
    assert level_for_score(score_metrics(metrics)) == "PULSE"


def test_score_never_goes_negative_and_season_is_monthly_utc() -> None:
    assert score_metrics(RatingMetrics(missed_reveals=99)) == 0
    start, end = season_window(datetime(2026, 12, 31, 23, 59, tzinfo=UTC))
    assert start == datetime(2026, 12, 1, tzinfo=UTC)
    assert end == datetime(2027, 1, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_rating_is_derived_from_verified_projection_rows(app) -> None:
    now = datetime.now(UTC)
    async with app.state.session_factory() as db:
        me = User(telegram_id=810_001, first_name="Me")
        friend = User(telegram_id=810_002, first_name="Friend")
        db.add_all([me, friend])
        await db.flush()

        referral = ReferralCode(code="rating-friend", owner_user_id=me.id)
        db.add(referral)
        await db.flush()
        db.add(
            ReferralAttribution(
                inviter_user_id=me.id,
                invitee_user_id=friend.id,
                code=referral.code,
                status="qualified",
                qualified_tx_hash="qualified-proof",
                qualified_at=now,
            )
        )

        position = BankPosition(
            position_id=81_001,
            user_id=me.id,
            owner_wallet="0:" + "1" * 64,
            network=-3,
            contract_address="0:" + "2" * 64,
            query_id=81_001,
            principal_nano=1,
            multiplier_bps=12_500,
            target_payout_nano=2,
            funded_amount_nano=2,
            remaining_amount_nano=0,
            queue_index=0,
            current_status=BankPositionStatus.PAYOUT_SENT.value,
        )
        db.add(position)
        await db.flush()
        db.add(
            BankPayout(
                position_id=position.id,
                network=-3,
                amount_nano=9_000_000_000_000,
                destination=position.owner_wallet,
                tx_hash="bank-rating-proof",
            )
        )

        offer_me = DuelOffer(
            onchain_offer_id=82_001,
            query_id=82_001,
            user_id=me.id,
            owner_wallet="0:" + "3" * 64,
            network=-3,
            contract_address="0:" + "4" * 64,
            chance_bps=5_000,
            total_pool_nano=2,
            stake_nano=1,
            opponent_stake_nano=1,
            fee_bps=250,
            payout_nano=2,
            commitment_hex="aa" * 32,
            state=OfferState.SETTLED.value,
            expires_at=now + timedelta(minutes=10),
        )
        offer_friend = DuelOffer(
            onchain_offer_id=82_002,
            query_id=82_002,
            user_id=friend.id,
            owner_wallet="0:" + "5" * 64,
            network=-3,
            contract_address="0:" + "4" * 64,
            chance_bps=5_000,
            total_pool_nano=2,
            stake_nano=1,
            opponent_stake_nano=1,
            fee_bps=250,
            payout_nano=2,
            commitment_hex="bb" * 32,
            state=OfferState.SETTLED.value,
            expires_at=now + timedelta(minutes=10),
        )
        db.add_all([offer_me, offer_friend])
        await db.flush()
        duel = Duel(
            onchain_duel_id=82_003,
            network=-3,
            offer_a_id=offer_me.id,
            offer_b_id=offer_friend.id,
            state=DuelState.SETTLED.value,
            reveal_deadline=now + timedelta(minutes=5),
            settled_tx_hash="duel-rating-proof",
            settled_at=now,
        )
        db.add(duel)
        await db.flush()
        db.add_all(
            [
                DuelPlayer(
                    duel_id=duel.id,
                    offer_id=offer_me.id,
                    user_id=me.id,
                    chance_bps=5_000,
                    stake_nano=1,
                ),
                DuelPlayer(
                    duel_id=duel.id,
                    offer_id=offer_friend.id,
                    user_id=friend.id,
                    chance_bps=5_000,
                    stake_nano=1,
                ),
                DuelReveal(
                    duel_id=duel.id,
                    offer_id=offer_me.id,
                    tx_hash="reveal-rating-proof",
                    created_at=now,
                ),
                DuelSettlement(
                    duel_id=duel.id,
                    winner_wallet=offer_me.owner_wallet,
                    payout_nano=2,
                    fee_nano=0,
                    outcome="settled",
                    tx_hash="duel-rating-proof",
                    created_at=now,
                ),
            ]
        )
        await db.commit()

        rating = await build_rating(db, me, now=now)

    assert rating.me.score == 205
    assert rating.me.level == "PULSE"
    assert rating.me.proofs == 2
    assert rating.me.reliability_bps == 10_000
    assert [entry.user_id for entry in rating.circle] == [me.id, friend.id]
    friend_entry = next(entry for entry in rating.leaderboard if entry.user_id == friend.id)
    assert friend_entry.score == 20
    assert friend_entry.missed_reveals == 1
