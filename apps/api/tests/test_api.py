import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from sqlalchemy import select

from app.models import Duel, MatchmakingOffer, OfferState, User, Wallet


def signed_init_data() -> str:
    values = {
        "auth_date": str(int(datetime.now(UTC).timestamp())),
        "query_id": "AAE-api",
        "user": json.dumps({"id": 777000111, "first_name": "Loop"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", b"123456:test-token", hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


@pytest.mark.asyncio
async def test_auth_me_and_social_cycle(client) -> None:
    auth = await client.post("/api/v1/auth/telegram", json={"init_data": signed_init_data()})
    assert auth.status_code == 200, auth.text
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["telegram_id"] == 777000111
    assert me.json()["bank"] is None
    assert "balance_nano" not in me.json()
    bank = await client.post("/api/v1/bank/cycles", headers=headers, json={"goal_events": 6})
    assert bank.status_code == 201
    assert bank.json()["sequence_number"] == 1
    assert bank.json()["event_count"] == 1
    assert bank.json()["progress_bps"] == 1_666
    assert bank.json()["events"][0]["kind"] == "cycle_started"
    assert (
        await client.post("/api/v1/bank/cycles", headers=headers, json={"goal_events": 6})
    ).status_code == 409
    refreshed = await client.get("/api/v1/me", headers=headers)
    assert refreshed.json()["bank"]["id"] == bank.json()["id"]


@pytest.mark.asyncio
async def test_quote_requires_verified_wallet(client, app) -> None:
    auth = await client.post("/api/v1/auth/telegram", json={"init_data": signed_init_data()})
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    denied = await client.post(
        "/api/v1/duels/quote",
        headers=headers,
        json={
            "offer_id": 12345,
            "chance_bps": 5000,
            "total_pool_nano": 4_000_000_000,
            "commitment_hex": "ab" * 32,
        },
    )
    assert denied.status_code == 409
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == 777000111))
        db.add(
            Wallet(
                user_id=user.id,
                network=-3,
                address="0:" + "22" * 32,
                public_key="33" * 32,
            )
        )
        await db.commit()
    quote = await client.post(
        "/api/v1/duels/quote",
        headers=headers,
        json={
            "offer_id": 12345,
            "chance_bps": 5000,
            "total_pool_nano": 4_000_000_000,
            "commitment_hex": "ab" * 32,
        },
    )
    assert quote.status_code == 200, quote.text
    result = quote.json()
    assert result["offer"]["stake_nano"] == 2_000_000_000
    assert result["transaction"]["amount_nano"] == "2050000000"


@pytest.mark.asyncio
async def test_duel_view_and_reveal_intent_never_expose_secret(client, app) -> None:
    auth = await client.post("/api/v1/auth/telegram", json={"init_data": signed_init_data()})
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == 777000111))
        opponent = User(telegram_id=777000222, first_name="Opponent")
        db.add(opponent)
        await db.flush()
        own_wallet = Wallet(
            user_id=user.id,
            network=-3,
            address="0:" + "22" * 32,
            public_key="33" * 32,
        )
        other_wallet = Wallet(
            user_id=opponent.id,
            network=-3,
            address="0:" + "44" * 32,
            public_key="55" * 32,
        )
        db.add_all([own_wallet, other_wallet])
        await db.flush()
        expires = datetime.now(UTC) + timedelta(minutes=15)
        own_offer = MatchmakingOffer(
            onchain_offer_id=701,
            user_id=user.id,
            wallet_id=own_wallet.id,
            network=-3,
            contract_address="0:" + "11" * 32,
            chance_bps=2500,
            total_pool_nano=4_000_000_000,
            stake_nano=1_000_000_000,
            commitment_hex="aa" * 32,
            state=OfferState.MATCHED.value,
            expires_at=expires,
        )
        other_offer = MatchmakingOffer(
            onchain_offer_id=702,
            user_id=opponent.id,
            wallet_id=other_wallet.id,
            network=-3,
            contract_address="0:" + "11" * 32,
            chance_bps=7500,
            total_pool_nano=4_000_000_000,
            stake_nano=3_000_000_000,
            commitment_hex="bb" * 32,
            state=OfferState.MATCHED.value,
            expires_at=expires,
        )
        db.add_all([own_offer, other_offer])
        await db.flush()
        db.add(
            Duel(
                onchain_duel_id=702,
                network=-3,
                offer_a_id=own_offer.id,
                offer_b_id=other_offer.id,
                reveal_deadline=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
        await db.commit()

    duels = await client.get("/api/v1/duels", headers=headers)
    assert duels.status_code == 200, duels.text
    assert duels.json()[0]["offer_id"] == 701
    intent = await client.post("/api/v1/duels/702/reveal-intent", headers=headers, json={})
    assert intent.status_code == 200, intent.text
    payload = intent.json()
    assert payload["operation"] == "reveal"
    assert payload["offer_id"] == 701
    assert "secret" not in payload
