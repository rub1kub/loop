import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import ReferralAttribution, ReferralCode, User, Wallet
from app.modules.duel.models import DuelInvitation, DuelOffer, OfferState
from app.ton import verify_direct_accept_permit


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


async def auth_headers(
    client, telegram_id: int, *, start_param: str | None = None
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": signed_init_data(telegram_id, start_param=start_param)},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def add_wallet(app, telegram_id: int, byte: str) -> Wallet:
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
        assert user is not None
        wallet = Wallet(
            user_id=user.id,
            network=-3,
            address="0:" + byte * 64,
            public_key=("a" if byte != "a" else "b") * 64,
        )
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)
        return wallet


def offer_for(
    user: User,
    wallet: Wallet,
    offer_id: int,
    *,
    chance_bps: int,
    stake_nano: int,
    opponent_stake_nano: int,
    mode: str = "afk",
) -> DuelOffer:
    return DuelOffer(
        onchain_offer_id=offer_id,
        query_id=offer_id,
        user_id=user.id,
        wallet_id=wallet.id,
        owner_wallet=wallet.address,
        network=-3,
        contract_address="0:" + "1" * 64,
        chance_bps=chance_bps,
        total_pool_nano=stake_nano + opponent_stake_nano,
        stake_nano=stake_nano,
        opponent_stake_nano=opponent_stake_nano,
        fee_bps=250,
        payout_nano=(stake_nano + opponent_stake_nano) * 9750 // 10_000,
        commitment_hex="ab" * 32,
        mode=mode,
        state=OfferState.OPEN.value,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


@pytest.mark.asyncio
async def test_authentication_and_wallet_challenge_are_fail_closed_and_one_time(
    client, app
) -> None:
    assert (await client.get("/api/v1/me")).status_code == 401
    assert (
        await client.post("/api/v1/auth/telegram", json={"init_data": "hash=00"})
    ).status_code == 401
    headers = await auth_headers(client, 700_001)
    updated = await client.patch(
        "/api/v1/me/settings",
        headers=headers,
        json={"onboarding_seen": True, "onboarding_enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["onboarding_enabled"] is False
    challenge = await client.post("/api/v1/wallet/challenge", headers=headers, json={})
    assert challenge.status_code == 200
    payload = challenge.json()["payload"]
    assert await app.state.challenge_store.consume(payload) is not None
    assert await app.state.challenge_store.consume(payload) is None


@pytest.mark.asyncio
async def test_quotes_reject_invalid_terms_and_second_active_operation(client, app) -> None:
    telegram_id = 700_002
    headers = await auth_headers(client, telegram_id)
    await add_wallet(app, telegram_id, "2")
    invalid = await client.post(
        "/api/v1/duels/offers/quote",
        headers=headers,
        json={
            "offer_id": 2001,
            "chance_bps": 3300,
            "stake_nano": 1_000_000_000,
            "commitment_hex": "ab" * 32,
        },
    )
    assert invalid.status_code == 422
    common = {
        "offer_id": 2001,
        "chance_bps": 5000,
        "stake_nano": 2_000_000_000,
        "commitment_hex": "ab" * 32,
    }
    created = await client.post("/api/v1/duels/offers/quote", headers=headers, json=common)
    assert created.status_code == 201, created.text
    second = await client.post(
        "/api/v1/duels/offers/quote", headers=headers, json={**common, "offer_id": 2002}
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_afk_matchmaking_selects_only_complementary_open_offer(client, app) -> None:
    first_id, second_id = 700_003, 700_004
    await auth_headers(client, first_id)
    second_headers = await auth_headers(client, second_id)
    first_wallet = await add_wallet(app, first_id, "3")
    await add_wallet(app, second_id, "4")
    async with app.state.session_factory() as db:
        first_user = await db.scalar(select(User).where(User.telegram_id == first_id))
        assert first_user is not None
        db.add(
            offer_for(
                first_user,
                first_wallet,
                3001,
                chance_bps=5000,
                stake_nano=1_000_000_000,
                opponent_stake_nano=1_000_000_000,
            )
        )
        await db.commit()
    quote = await client.post(
        "/api/v1/duels/offers/quote",
        headers=second_headers,
        json={
            "offer_id": 3002,
            "chance_bps": 5000,
            "stake_nano": 1_000_000_000,
            "commitment_hex": "ef" * 32,
        },
    )
    assert quote.status_code == 201, quote.text
    assert quote.json()["transaction"]["counter_offer_id"] == 3001


@pytest.mark.asyncio
async def test_new_asymmetric_duel_offer_is_rejected(client, app) -> None:
    telegram_id = 700_011
    headers = await auth_headers(client, telegram_id)
    await add_wallet(app, telegram_id, "b")
    quote = await client.post(
        "/api/v1/duels/offers/quote",
        headers=headers,
        json={
            "offer_id": 3011,
            "chance_bps": 2500,
            "stake_nano": 1_000_000_000,
            "commitment_hex": "ad" * 32,
            "mode": "afk",
        },
    )
    assert quote.status_code == 422
    assert "50/50" in quote.text


@pytest.mark.asyncio
async def test_direct_quote_creates_the_onchain_invite_id_before_inline_sharing(
    client, app
) -> None:
    telegram_id = 700_010
    headers = await auth_headers(client, telegram_id)
    await add_wallet(app, telegram_id, "a")
    quote = await client.post(
        "/api/v1/duels/offers/quote",
        headers=headers,
        json={
            "offer_id": 3010,
            "chance_bps": 5000,
            "stake_nano": 1_000_000_000,
            "commitment_hex": "ac" * 32,
            "mode": "direct",
        },
    )
    assert quote.status_code == 201, quote.text
    transaction = quote.json()["transaction"]
    assert transaction["operation"] == "open_direct_offer"
    assert len(transaction["invite_id_hex"]) == 64
    assert transaction["direct_signature_hex"] is None
    async with app.state.session_factory() as db:
        invitation = await db.scalar(select(DuelInvitation))
        offer = await db.scalar(select(DuelOffer).where(DuelOffer.onchain_offer_id == 3010))
        assert invitation is not None and offer is not None
        assert invitation.invite_id_hex == transaction["invite_id_hex"]
        assert offer.invite_id_hex == invitation.invite_id_hex


@pytest.mark.asyncio
async def test_direct_invitation_is_explicitly_accepted_and_cannot_be_stolen(client, app) -> None:
    owner_id, receiver_id, third_id = 700_005, 700_006, 700_007
    owner_headers = await auth_headers(client, owner_id)
    receiver_headers = await auth_headers(client, receiver_id)
    third_headers = await auth_headers(client, third_id)
    owner_wallet = await add_wallet(app, owner_id, "5")
    await add_wallet(app, receiver_id, "6")
    async with app.state.session_factory() as db:
        owner = await db.scalar(select(User).where(User.telegram_id == owner_id))
        assert owner is not None
        offer = offer_for(
            owner,
            owner_wallet,
            4001,
            chance_bps=7500,
            stake_nano=3_000_000_000,
            opponent_stake_nano=1_000_000_000,
            mode="direct",
        )
        offer.invite_id_hex = "4d" * 32
        db.add(offer)
        await db.flush()
        db.add(
            DuelInvitation(
                code="direct-loop-4001",
                creator_user_id=owner.id,
                creator_offer_id=offer.id,
                invite_id_hex="4d" * 32,
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
        await db.commit()
    assert (
        await client.get("/api/v1/invites/direct-loop-4001", headers=owner_headers)
    ).status_code == 409
    preview = await client.get("/api/v1/invites/direct-loop-4001", headers=receiver_headers)
    assert preview.status_code == 200
    accepted = await client.post(
        "/api/v1/invites/direct-loop-4001/accept", headers=receiver_headers
    )
    assert accepted.status_code == 200
    assert (
        await client.post("/api/v1/invites/direct-loop-4001/accept", headers=third_headers)
    ).status_code == 409
    quote = await client.post(
        "/api/v1/duels/offers/quote",
        headers=receiver_headers,
        json={
            "offer_id": 4002,
            "chance_bps": 2500,
            "stake_nano": 1_000_000_000,
            "commitment_hex": "cd" * 32,
            "challenge_code": "direct-loop-4001",
        },
    )
    assert quote.status_code == 201, quote.text
    transaction = quote.json()["transaction"]
    assert transaction["operation"] == "accept_direct_offer"
    assert transaction["counter_offer_id"] == 4001
    assert transaction["direct_counter_offer_id"] == 4001
    assert verify_direct_accept_permit(
        get_settings().duel_invite_public_key,
        transaction["direct_signature_hex"],
        network=-3,
        contract_address=transaction["contract_address"],
        invite_id_hex="4d" * 32,
        counter_offer_id=4001,
        invited_address="0:" + "6" * 64,
        valid_until=transaction["direct_valid_until"],
    )

    async with app.state.session_factory() as db:
        creator_offer = await db.scalar(
            select(DuelOffer).where(DuelOffer.onchain_offer_id == 4001)
        )
        receiver_offer = await db.scalar(
            select(DuelOffer).where(DuelOffer.onchain_offer_id == 4002)
        )
        assert creator_offer is not None and receiver_offer is not None
        creator_offer.reserved_until = datetime.now(UTC) - timedelta(seconds=1)
        receiver_offer.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    assert (
        await client.post("/api/v1/invites/direct-loop-4001/accept", headers=receiver_headers)
    ).status_code == 200
    retry = await client.post(
        "/api/v1/duels/offers/quote",
        headers=receiver_headers,
        json={
            "offer_id": 4003,
            "chance_bps": 2500,
            "stake_nano": 1_000_000_000,
            "commitment_hex": "ce" * 32,
            "challenge_code": "direct-loop-4001",
        },
    )
    assert retry.status_code == 201, retry.text
    assert retry.json()["transaction"]["operation"] == "accept_direct_offer"


@pytest.mark.asyncio
async def test_referral_attribution_is_once_only_and_not_self_referential(client, app) -> None:
    inviter_id, invitee_id = 700_008, 700_009
    await auth_headers(client, inviter_id)
    async with app.state.session_factory() as db:
        inviter = await db.scalar(select(User).where(User.telegram_id == inviter_id))
        assert inviter is not None
        db.add(ReferralCode(code="looprefcode", owner_user_id=inviter.id))
        await db.commit()
    await auth_headers(client, invitee_id, start_param="ref_looprefcode")
    await auth_headers(client, invitee_id, start_param="ref_looprefcode")
    async with app.state.session_factory() as db:
        rows = (await db.scalars(select(ReferralAttribution))).all()
        assert len(rows) == 1
        assert rows[0].status == "pending"


@pytest.mark.asyncio
async def test_non_business_endpoints_are_fail_closed(client) -> None:
    assert (await client.get("/live")).json() == {"status": "ok"}
    assert (await client.get("/metrics")).status_code == 200
    webhook = await client.post("/api/internal/telegram/webhook", json={})
    assert webhook.status_code == 403
