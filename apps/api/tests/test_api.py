import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from sqlalchemy import select

from app.models import User, Wallet
from app.modules.duel.models import Duel, DuelOffer, OfferState
from app.ton import ContractState, JettonWalletState


def signed_init_data(telegram_id: int = 777000111) -> str:
    values = {
        "auth_date": str(int(datetime.now(UTC).timestamp())),
        "query_id": f"AAE-api-{telegram_id}",
        "user": json.dumps({"id": telegram_id, "first_name": "Loop"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", b"123456:test-token", hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


async def authenticate(client, telegram_id: int = 777000111) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/telegram", json={"init_data": signed_init_data(telegram_id)}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def add_wallet(app, telegram_id: int, byte: str = "2") -> Wallet:
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
        assert user is not None
        wallet = Wallet(
            user_id=user.id,
            network=-3,
            address="0:" + byte * 64,
            public_key="3" * 64,
        )
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)
        return wallet


@pytest.mark.asyncio
async def test_auth_profile_has_separate_bank_and_duel_domains(client) -> None:
    headers = await authenticate(client)
    me = await client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["bank"] == {"active": 0, "completed": 0, "total": 0}
    assert me.json()["duel"] == {"active": 0, "completed": 0, "total": 0}
    assert "balance_nano" not in me.json()
    assert (await client.post("/api/v1/bank/cycles", headers=headers, json={})).status_code == 404


@pytest.mark.asyncio
async def test_bank_quote_is_testnet_only_and_requires_verified_wallet(client, app) -> None:
    headers = await authenticate(client)
    payload = {
        "position_id": 1001,
        "principal_nano": 2_000_000_000,
        "multiplier_bps": 15_000,
    }
    denied = await client.post("/api/v1/bank/positions/quote", headers=headers, json=payload)
    assert denied.status_code == 409
    await add_wallet(app, 777000111)
    quote = await client.post("/api/v1/bank/positions/quote", headers=headers, json=payload)
    assert quote.status_code == 201, quote.text
    result = quote.json()
    assert result["position"]["target_payout_nano"] == 3_000_000_000
    assert result["transaction"]["operation"] == "create_bank_position"
    assert result["transaction"]["amount_nano"] == "2080000000"
    assert (await client.get("/api/v1/bank/positions/current", headers=headers)).json()[
        "position_id"
    ] == 1001


@pytest.mark.asyncio
async def test_duel_quote_uses_requested_stake_and_complementary_terms(client, app) -> None:
    headers = await authenticate(client)
    await add_wallet(app, 777000111)
    quote = await client.post(
        "/api/v1/duels/offers/quote",
        headers=headers,
        json={
            "offer_id": 12345,
            "chance_bps": 2500,
            "stake_nano": 1_000_000_001,
            "commitment_hex": "ab" * 32,
            "mode": "afk",
        },
    )
    assert quote.status_code == 201, quote.text
    result = quote.json()
    assert result["offer"]["stake_nano"] == 1_000_000_001
    assert result["offer"]["opponent_stake_nano"] == 3_000_000_003
    assert result["offer"]["total_pool_nano"] == 4_000_000_004
    assert result["transaction"]["amount_nano"] == "1050000001"


@pytest.mark.asyncio
async def test_duel_views_and_intents_never_expose_commit_reveal_secret(client, app) -> None:
    headers = await authenticate(client)
    own_wallet = await add_wallet(app, 777000111)
    await authenticate(client, 777000222)
    other_wallet = await add_wallet(app, 777000222, "4")
    async with app.state.session_factory() as db:
        own_user = await db.scalar(select(User).where(User.telegram_id == 777000111))
        other_user = await db.scalar(select(User).where(User.telegram_id == 777000222))
        assert own_user is not None and other_user is not None
        expires = datetime.now(UTC) + timedelta(minutes=15)
        common = {
            "query_id": 701,
            "network": -3,
            "contract_address": "0:" + "1" * 64,
            "total_pool_nano": 4_000_000_000,
            "opponent_stake_nano": 3_000_000_000,
            "fee_bps": 250,
            "payout_nano": 3_900_000_000,
            "mode": "afk",
            "state": OfferState.MATCHED.value,
            "expires_at": expires,
        }
        own_offer = DuelOffer(
            **common,
            onchain_offer_id=701,
            user_id=own_user.id,
            wallet_id=own_wallet.id,
            owner_wallet=own_wallet.address,
            chance_bps=2500,
            stake_nano=1_000_000_000,
            commitment_hex="aa" * 32,
        )
        other_offer = DuelOffer(
            **{**common, "query_id": 702, "opponent_stake_nano": 1_000_000_000},
            onchain_offer_id=702,
            user_id=other_user.id,
            wallet_id=other_wallet.id,
            owner_wallet=other_wallet.address,
            chance_bps=7500,
            stake_nano=3_000_000_000,
            commitment_hex="bb" * 32,
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

    response = await client.get("/api/v1/duels", headers=headers)
    assert response.status_code == 200, response.text
    assert "secret" not in json.dumps(response.json())
    intent = await client.post("/api/v1/duels/702/reveal-intent", headers=headers, json={})
    assert intent.status_code == 200, intent.text
    assert intent.json()["offer_id"] == 701
    assert "secret" not in intent.json()


@pytest.mark.asyncio
async def test_onchain_diagnostics_are_scoped_by_mode_and_network(client, app) -> None:
    class FakeTonClient:
        async def get_contract_state(self, address: str) -> ContractState:
            return ContractState(
                address=address,
                status="active",
                balance_nano=123,
                code_hash="AA" * 32,
                last_transaction_hash="proof-hash",
                last_transaction_lt=99,
            )

        async def get_native_balance(self, address: str) -> int:
            return 456

        async def get_jetton_wallet(
            self, owner_address: str, jetton_master: str
        ) -> JettonWalletState:
            return JettonWalletState(
                owner_address=owner_address,
                jetton_master=jetton_master,
                wallet_address="0:" + "4" * 64,
                balance_nano=789,
            )

    fake = FakeTonClient()
    app.state.ton_client = fake
    app.state.plush_ton_client = fake
    headers = await authenticate(client)
    await add_wallet(app, 777000111)
    for mode in ("bank", "duel"):
        response = await client.get(f"/api/v1/onchain/contracts/{mode}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["mode"] == mode
        assert response.json()["network"] == -3
        assert response.json()["wallet_balance_nano"] == 456
