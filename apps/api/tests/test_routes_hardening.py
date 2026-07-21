import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from sqlalchemy import select

from app.models import (
    ChallengeState,
    Duel,
    DuelChallenge,
    MatchmakingOffer,
    OfferState,
    User,
    Wallet,
)


def signed_init_data(telegram_id: int, *, start_param: str | None = None) -> str:
    values = {
        "auth_date": str(int(datetime.now(UTC).timestamp())),
        "query_id": f"AAE-{telegram_id}",
        "user": json.dumps(
            {"id": telegram_id, "first_name": f"User {telegram_id}"}, separators=(",", ":")
        ),
    }
    if start_param:
        values["start_param"] = start_param
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", b"123456:test-token", hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


async def auth_headers(client, telegram_id: int = 700_001) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/telegram", json={"init_data": signed_init_data(telegram_id)}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def add_wallet(app, telegram_id: int, byte: str, *, active: bool = True) -> Wallet:
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
        assert user is not None
        wallet = Wallet(
            user_id=user.id,
            network=-3,
            address="0:" + byte * 32,
            public_key=("a" if byte != "a" else "b") * 64,
            active=active,
        )
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)
        return wallet


@pytest.mark.asyncio
async def test_authentication_validation_and_one_time_wallet_challenge(client, app) -> None:
    assert (await client.get("/api/v1/me")).status_code == 401
    forged = await client.post("/api/v1/auth/telegram", json={"init_data": "hash=00"})
    assert forged.status_code == 401

    headers = await auth_headers(client)
    invalid_bank = await client.post(
        "/api/v1/bank/cycles", headers=headers, json={"goal_events": 2}
    )
    assert invalid_bank.status_code == 422
    updated = await client.patch(
        "/api/v1/me/settings", headers=headers, json={"onboarding_seen": True}
    )
    assert updated.status_code == 200
    assert updated.json()["onboarding_seen"] is True

    challenge = await client.post("/api/v1/wallet/challenge", headers=headers, json={})
    assert challenge.status_code == 200
    payload = challenge.json()["payload"]
    stored = await app.state.challenge_store.consume(payload)
    assert stored is not None and stored["network"] == -3
    assert await app.state.challenge_store.consume(payload) is None


@pytest.mark.asyncio
async def test_quote_rejects_bad_pool_active_wallet_and_reused_id(client, app) -> None:
    telegram_id = 700_002
    headers = await auth_headers(client, telegram_id)
    await add_wallet(app, telegram_id, "2")
    common = {
        "offer_id": 2_001,
        "chance_bps": 5000,
        "total_pool_nano": 4_000_000_000,
        "commitment_hex": "ab" * 32,
    }
    uneven = await client.post(
        "/api/v1/duels/quote",
        headers=headers,
        json={**common, "total_pool_nano": 4_000_000_002},
    )
    assert uneven.status_code == 422
    outside = await client.post(
        "/api/v1/duels/quote",
        headers=headers,
        json={**common, "total_pool_nano": 400_000_000},
    )
    assert outside.status_code == 422
    weighted = await client.post(
        "/api/v1/duels/quote",
        headers=headers,
        json={**common, "chance_bps": 2500},
    )
    assert weighted.status_code == 422

    created = await client.post("/api/v1/duels/quote", headers=headers, json=common)
    assert created.status_code == 200, created.text
    second = await client.post(
        "/api/v1/duels/quote", headers=headers, json={**common, "offer_id": 2_002}
    )
    assert second.status_code == 409

    async with app.state.session_factory() as db:
        offer = await db.scalar(
            select(MatchmakingOffer).where(MatchmakingOffer.onchain_offer_id == 2_001)
        )
        assert offer is not None
        offer.state = OfferState.CANCELLED.value
        await db.commit()
    duplicate = await client.post("/api/v1/duels/quote", headers=headers, json=common)
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_quote_selects_only_complementary_open_counterparty(client, app) -> None:
    first_id, second_id = 700_003, 700_004
    await auth_headers(client, first_id)
    second_headers = await auth_headers(client, second_id)
    first_wallet = await add_wallet(app, first_id, "3")
    await add_wallet(app, second_id, "4")
    async with app.state.session_factory() as db:
        first_user = await db.scalar(select(User).where(User.telegram_id == first_id))
        assert first_user is not None
        db.add(
            MatchmakingOffer(
                onchain_offer_id=3_001,
                user_id=first_user.id,
                wallet_id=first_wallet.id,
                network=-3,
                contract_address="0:" + "11" * 32,
                chance_bps=5000,
                total_pool_nano=4_000_000_000,
                stake_nano=2_000_000_000,
                commitment_hex="cd" * 32,
                state=OfferState.OPEN.value,
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
        await db.commit()

    quote = await client.post(
        "/api/v1/duels/quote",
        headers=second_headers,
        json={
            "offer_id": 3_002,
            "chance_bps": 5000,
            "total_pool_nano": 4_000_000_000,
            "commitment_hex": "ef" * 32,
        },
    )
    assert quote.status_code == 200, quote.text
    assert quote.json()["transaction"]["counter_offer_id"] == 3_001


@pytest.mark.asyncio
async def test_action_intents_enforce_ownership_state_and_deadlines(client, app) -> None:
    own_id, other_id = 700_005, 700_006
    headers = await auth_headers(client, own_id)
    await auth_headers(client, other_id)
    own_wallet = await add_wallet(app, own_id, "5")
    other_wallet = await add_wallet(app, other_id, "6")
    async with app.state.session_factory() as db:
        own_user = await db.scalar(select(User).where(User.telegram_id == own_id))
        other_user = await db.scalar(select(User).where(User.telegram_id == other_id))
        assert own_user is not None and other_user is not None
        own_offer = MatchmakingOffer(
            onchain_offer_id=4_001,
            user_id=own_user.id,
            wallet_id=own_wallet.id,
            network=-3,
            contract_address="0:" + "11" * 32,
            chance_bps=2500,
            total_pool_nano=4_000_000_000,
            stake_nano=1_000_000_000,
            commitment_hex="11" * 32,
            state=OfferState.MATCHED.value,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        other_offer = MatchmakingOffer(
            onchain_offer_id=4_002,
            user_id=other_user.id,
            wallet_id=other_wallet.id,
            network=-3,
            contract_address="0:" + "11" * 32,
            chance_bps=7500,
            total_pool_nano=4_000_000_000,
            stake_nano=3_000_000_000,
            commitment_hex="22" * 32,
            state=OfferState.MATCHED.value,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db.add_all([own_offer, other_offer])
        await db.flush()
        duel = Duel(
            onchain_duel_id=4_002,
            network=-3,
            offer_a_id=own_offer.id,
            offer_b_id=other_offer.id,
            reveal_deadline=datetime.now(UTC) + timedelta(minutes=5),
        )
        db.add(duel)
        await db.commit()

    assert (
        await client.post("/api/v1/duels/offers/4001/cancel-intent", headers=headers, json={})
    ).status_code == 409
    assert (
        await client.post("/api/v1/duels/9999/reveal-intent", headers=headers, json={})
    ).status_code == 404
    assert (
        await client.post("/api/v1/duels/4002/expire-intent", headers=headers, json={})
    ).status_code == 409

    async with app.state.session_factory() as db:
        duel = await db.scalar(select(Duel).where(Duel.onchain_duel_id == 4_002))
        assert duel is not None
        duel.reveal_deadline = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    expired = await client.post(
        "/api/v1/duels/4002/expire-intent", headers=headers, json={}
    )
    assert expired.status_code == 200
    assert expired.json()["operation"] == "expire_duel"
    assert (
        await client.post("/api/v1/duels/4002/reveal-intent", headers=headers, json={})
    ).status_code == 409


@pytest.mark.asyncio
async def test_bound_challenges_and_referrals_resist_self_use_expiry_and_double_accept(
    client, app
) -> None:
    owner_id, referred_id, third_id = 700_007, 700_008, 700_009
    owner_headers = await auth_headers(client, owner_id)
    referred_headers = await auth_headers(client, referred_id)
    third_headers = await auth_headers(client, third_id)
    async with app.state.session_factory() as db:
        owner = await db.scalar(select(User).where(User.telegram_id == owner_id))
        referred = await db.scalar(select(User).where(User.telegram_id == referred_id))
        assert owner is not None and referred is not None
        referred.referred_by_id = owner.id
        owner_wallet = Wallet(
            user_id=owner.id,
            network=-3,
            address="0:" + "7" * 32,
            public_key="6" * 64,
        )
        wallet = Wallet(
            user_id=referred.id,
            network=-3,
            address="0:" + "8" * 32,
            public_key="9" * 64,
        )
        db.add_all([owner_wallet, wallet])
        await db.flush()
        settled_offer = MatchmakingOffer(
            onchain_offer_id=5_001,
            user_id=referred.id,
            wallet_id=wallet.id,
            network=-3,
            contract_address="0:" + "11" * 32,
            chance_bps=5000,
            total_pool_nano=4_000_000_000,
            stake_nano=2_000_000_000,
            commitment_hex="33" * 32,
            state=OfferState.SETTLED.value,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        )
        owner_offer = MatchmakingOffer(
            onchain_offer_id=5_002,
            user_id=owner.id,
            wallet_id=owner_wallet.id,
            network=-3,
            contract_address="0:" + "11" * 32,
            chance_bps=5000,
            total_pool_nano=4_000_000_000,
            stake_nano=2_000_000_000,
            commitment_hex="44" * 32,
            state=OfferState.OPEN.value,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        third_creator = User(telegram_id=99, first_name="Creator")
        db.add_all([settled_offer, owner_offer, third_creator])
        await db.flush()
        third_wallet = Wallet(
            user_id=third_creator.id,
            network=-3,
            address="0:" + "a" * 32,
            public_key="b" * 64,
        )
        db.add(third_wallet)
        await db.flush()
        open_offer = MatchmakingOffer(
            onchain_offer_id=5_003,
            user_id=third_creator.id,
            wallet_id=third_wallet.id,
            network=-3,
            contract_address="0:" + "11" * 32,
            chance_bps=5000,
            total_pool_nano=4_000_000_000,
            stake_nano=2_000_000_000,
            commitment_hex="55" * 32,
            state=OfferState.OPEN.value,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        expired_offer = MatchmakingOffer(
            onchain_offer_id=5_004,
            user_id=third_creator.id,
            wallet_id=third_wallet.id,
            network=-3,
            contract_address="0:" + "11" * 32,
            chance_bps=5000,
            total_pool_nano=4_000_000_000,
            stake_nano=2_000_000_000,
            commitment_hex="66" * 32,
            state=OfferState.CANCELLED.value,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.add_all([open_offer, expired_offer])
        await db.flush()
        db.add_all(
            [
                DuelChallenge(
                    code="self-invite",
                    creator_user_id=owner.id,
                    creator_offer_id=owner_offer.id,
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                ),
                DuelChallenge(
                    code="open-invite",
                    creator_user_id=third_creator.id,
                    creator_offer_id=open_offer.id,
                    expires_at=datetime.now(UTC) + timedelta(minutes=5),
                ),
                DuelChallenge(
                    code="old-invite",
                    creator_user_id=third_creator.id,
                    creator_offer_id=expired_offer.id,
                    state=ChallengeState.OPEN.value,
                    expires_at=datetime.now(UTC) - timedelta(seconds=1),
                ),
            ]
        )
        await db.commit()

    referral = await client.get("/api/v1/referrals", headers=owner_headers)
    assert referral.status_code == 200
    assert referral.json()["invited"] == 1
    assert referral.json()["qualified"] == 1
    assert referral.json()["reward_points"] == 100
    assert (
        await client.get("/api/v1/invites/self-invite", headers=owner_headers)
    ).status_code == 409
    assert (
        await client.get("/api/v1/invites/old-invite", headers=referred_headers)
    ).status_code == 404
    accepted = await client.get("/api/v1/invites/open-invite", headers=referred_headers)
    assert accepted.status_code == 200
    assert accepted.json()["creator_name"] == "Creator"
    assert accepted.json()["counter_offer_id"] == 5_003
    bound = await client.post(
        "/api/v1/duels/quote",
        headers=referred_headers,
        json={
            "offer_id": 5_005,
            "chance_bps": 5000,
            "total_pool_nano": 4_000_000_000,
            "commitment_hex": "77" * 32,
            "challenge_code": "open-invite",
        },
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["transaction"]["counter_offer_id"] == 5_003
    assert (
        await client.get("/api/v1/invites/open-invite", headers=third_headers)
    ).status_code == 409


@pytest.mark.asyncio
async def test_non_business_endpoints_are_fail_closed(client) -> None:
    assert (await client.get("/live")).json() == {"status": "ok"}
    assert (await client.get("/metrics")).status_code == 200
    webhook = await client.post("/api/internal/telegram/webhook", json={})
    assert webhook.status_code == 403
