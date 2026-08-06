import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import User, Wallet
from app.modules.bank.router import GRAM, maturity_limit
from app.modules.duel.models import Duel, DuelOffer, DuelState, OfferState
from app.ton import (
    ContractAdminState,
    ContractState,
    JettonWalletState,
    verify_holder_fee_permit,
)


def signed_init_data(
    telegram_id: int = 777000111,
    *,
    photo_url: str | None = None,
    start_param: str | None = None,
) -> str:
    user = {"id": telegram_id, "first_name": "Loop"}
    if photo_url:
        user["photo_url"] = photo_url
    values = {
        "auth_date": str(int(datetime.now(UTC).timestamp())),
        "query_id": f"AAE-api-{telegram_id}",
        "user": json.dumps(user, separators=(",", ":")),
    }
    if start_param:
        values["start_param"] = start_param
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
async def test_avatar_is_proxied_through_authenticated_same_origin_api(
    client, app, monkeypatch
) -> None:
    photo_url = "https://t.me/i/userpic/320/loop.jpg"
    auth = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": signed_init_data(777000112, photo_url=photo_url)},
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    upstream = httpx.Response(
        status_code=200,
        headers={"Content-Type": "image/jpeg"},
        content=b"\xff\xd8\xff\xd9",
        request=httpx.Request("GET", "https://cdn4.telesco.pe/file/loop.jpg"),
    )
    get = AsyncMock(return_value=upstream)
    monkeypatch.setattr(app.state.http, "get", get)

    assert (await client.get("/api/v1/me/avatar")).status_code == 401
    response = await client.get("/api/v1/me/avatar", headers=headers)

    assert response.status_code == 200
    assert response.content == b"\xff\xd8\xff\xd9"
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, max-age=300"
    get.assert_awaited_once_with(photo_url, follow_redirects=True)


@pytest.mark.asyncio
async def test_avatar_proxy_rejects_untrusted_photo_host(client, app, monkeypatch) -> None:
    auth = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": signed_init_data(777000113, photo_url="https://example.com/avatar.jpg")},
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    get = AsyncMock()
    monkeypatch.setattr(app.state.http, "get", get)

    response = await client.get("/api/v1/me/avatar", headers=headers)

    assert response.status_code == 404
    get.assert_not_awaited()


@pytest.mark.asyncio
async def test_rating_starts_transparently_without_money_metrics(client) -> None:
    headers = await authenticate(client)
    response = await client.get("/api/v1/rating", headers=headers)
    assert response.status_code == 200, response.text
    rating = response.json()
    assert rating["me"]["score"] == 0
    assert rating["me"]["rank"] == 1
    assert rating["me"]["proofs"] == 0
    # active_participants counts everyone registered, so authenticating for
    # this request is itself the one participant. The other tiles stay at zero
    # because nothing has been staked — which is the distinction the two tiles
    # exist to draw.
    assert rating["pulse"] == {
        "active_participants": 1,
        "active_bank": 0,
        "active_duels": 0,
        "proofs_24h": 0,
    }
    assert {item["code"] for item in rating["formula"]} == {
        "bank_payout",
        "duel_settlement",
        "timely_reveal",
        "qualified_referral",
        "missed_reveal",
    }
    assert "stake" not in json.dumps(rating)
    assert "profit" not in json.dumps(rating)


@pytest.mark.asyncio
async def test_bank_quote_is_testnet_only_and_requires_verified_wallet(client, app) -> None:
    headers = await authenticate(client)
    # A fresh queue caps deposits at one GRAM, so the amount has to sit under
    # the cap for the wallet check to be what rejects this.
    payload = {
        "position_id": 1001,
        "principal_nano": 1_000_000_000,
        "multiplier_bps": 15_000,
    }
    denied = await client.post("/api/v1/bank/positions/quote", headers=headers, json=payload)
    assert denied.status_code == 409
    await add_wallet(app, 777000111)
    quote = await client.post("/api/v1/bank/positions/quote", headers=headers, json=payload)
    assert quote.status_code == 201, quote.text
    result = quote.json()
    assert result["position"]["target_payout_nano"] == 1_500_000_000
    assert result["transaction"]["operation"] == "create_bank_position"
    assert result["transaction"]["amount_nano"] == "1080000000"
    assert (await client.get("/api/v1/bank/positions/current", headers=headers)).json()[
        "position_id"
    ] == 1001


@pytest.mark.asyncio
async def test_bank_debug_progress_is_scoped_and_never_persisted(client, app) -> None:
    from app.modules.bank.models import BankPosition, BankPositionStatus

    telegram_id = 777000111
    settings = get_settings()
    settings.bank_debug_telegram_ids = str(telegram_id)
    settings.bank_debug_progress_bps = 6_200
    headers = await authenticate(client, telegram_id)
    wallet = await add_wallet(app, telegram_id)

    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
        assert user is not None
        position = BankPosition(
            position_id=1062,
            query_id=1062,
            user_id=user.id,
            wallet_id=wallet.id,
            owner_wallet=wallet.address,
            network=settings.ton_network_id,
            contract_address=settings.bank_contract_address,
            principal_nano=1_000_000_000,
            multiplier_bps=12_500,
            target_payout_nano=1_250_000_000,
            funded_amount_nano=0,
            remaining_amount_nano=1_250_000_000,
            current_status=BankPositionStatus.QUEUED.value,
        )
        db.add(position)
        await db.commit()
        position_id = position.id

    current = await client.get("/api/v1/bank/positions/current", headers=headers)
    assert current.status_code == 200
    assert current.json()["progress_bps"] == 6_200
    assert current.json()["funded_amount_nano"] == 775_000_000
    assert current.json()["remaining_amount_nano"] == 475_000_000
    history = await client.get("/api/v1/bank/positions", headers=headers)
    assert history.json()[0]["progress_bps"] == 6_200
    assert settings.bank_debug_progress_for(telegram_id + 1) is None

    async with app.state.session_factory() as db:
        stored = await db.get(BankPosition, position_id)
        assert stored is not None
        assert stored.funded_amount_nano == 0
        assert stored.remaining_amount_nano == 1_250_000_000


@pytest.mark.parametrize(
    ("completed", "current", "next_limit", "remaining"),
    [
        # A cap of N GRAM unlocks after 5N payouts. Both ends of every rung so
        # an off-by-one in either implementation shows up here.
        (0, 1, 2, 10),
        (9, 1, 2, 1),
        (10, 2, 3, 5),
        (15, 3, 5, 10),
        (25, 5, 7, 10),
        (35, 7, 10, 15),
        (50, 10, 15, 25),
        (100, 20, 30, 50),
        (250, 50, 75, 125),
        (499, 75, 100, 1),
        (500, 100, None, None),
        (10_000, 100, None, None),
    ],
)
def test_bank_api_limit_schedule_matches_contract(
    completed: int,
    current: int,
    next_limit: int | None,
    remaining: int | None,
) -> None:
    assert maturity_limit(completed) == (
        current * GRAM,
        next_limit * GRAM if next_limit is not None else None,
        remaining,
    )


@pytest.mark.asyncio
async def test_early_bank_rejects_oversized_position_before_wallet_confirmation(
    client, app
) -> None:
    headers = await authenticate(client)
    await add_wallet(app, 777000111)
    limits = await client.get("/api/v1/bank/limits", headers=headers)
    assert limits.status_code == 200
    assert limits.json()["principal_limit_nano"] == 1_000_000_000
    denied = await client.post(
        "/api/v1/bank/positions/preview",
        headers=headers,
        json={"principal_nano": 1_000_000_001, "multiplier_bps": 12_500},
    )
    assert denied.status_code == 422
    assert denied.json()["detail"] == "Сейчас можно внести от 1 до 1 GRAM"


@pytest.mark.asyncio
async def test_duel_quote_uses_equal_terms_for_new_offers(client, app) -> None:
    headers = await authenticate(client)
    await add_wallet(app, 777000111)
    quote = await client.post(
        "/api/v1/duels/offers/quote",
        headers=headers,
        json={
            "offer_id": 12345,
            "chance_bps": 5000,
            "stake_nano": 1_000_000_001,
            "commitment_hex": "ab" * 32,
            "mode": "afk",
        },
    )
    assert quote.status_code == 201, quote.text
    result = quote.json()
    assert result["offer"]["stake_nano"] == 1_000_000_002
    assert result["offer"]["opponent_stake_nano"] == 1_000_000_002
    assert result["offer"]["total_pool_nano"] == 2_000_000_004
    assert result["transaction"]["amount_nano"] == "1050000002"


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
                state=DuelState.REVEALING.value,
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
async def test_duel_boost_intent_is_revision_and_probability_bound(client, app) -> None:
    headers = await authenticate(client)
    own_wallet = await add_wallet(app, 777000111)
    await authenticate(client, 777000222)
    other_wallet = await add_wallet(app, 777000222, "4")
    now = datetime.now(UTC)
    async with app.state.session_factory() as db:
        own_user = await db.scalar(select(User).where(User.telegram_id == 777000111))
        other_user = await db.scalar(select(User).where(User.telegram_id == 777000222))
        assert own_user is not None and other_user is not None
        common = {
            "network": -3,
            "contract_address": "0:" + "1" * 64,
            "chance_bps": 5_000,
            "total_pool_nano": 2_000_000_000,
            "stake_nano": 1_000_000_000,
            "opponent_stake_nano": 1_000_000_000,
            "fee_bps": 250,
            "payout_nano": 1_950_000_000,
            "state": OfferState.MATCHED.value,
            "expires_at": now + timedelta(minutes=15),
        }
        own_offer = DuelOffer(
            **common,
            onchain_offer_id=801,
            query_id=801,
            user_id=own_user.id,
            wallet_id=own_wallet.id,
            owner_wallet=own_wallet.address,
            commitment_hex="ca" * 32,
        )
        other_offer = DuelOffer(
            **common,
            onchain_offer_id=802,
            query_id=802,
            user_id=other_user.id,
            wallet_id=other_wallet.id,
            owner_wallet=other_wallet.address,
            commitment_hex="cb" * 32,
        )
        db.add_all([own_offer, other_offer])
        await db.flush()
        db.add(
            Duel(
                onchain_duel_id=802,
                network=-3,
                offer_a_id=own_offer.id,
                offer_b_id=other_offer.id,
                state=DuelState.BOOSTING.value,
                boost_deadline=now + timedelta(seconds=60),
                hard_deadline=now + timedelta(seconds=180),
                reveal_deadline=now + timedelta(seconds=360),
            )
        )
        await db.commit()

    intent = await client.post(
        "/api/v1/duels/802/boost-intent",
        headers=headers,
        json={
            "amount_nano": 500_000_000,
            "expected_revision": 0,
            "min_chance_bps": 6_000,
        },
    )
    assert intent.status_code == 200, intent.text
    assert intent.json()["amount_nano"] == "550000000"
    assert intent.json()["boost_nano"] == "500000000"
    assert intent.json()["min_chance_bps"] == 6_000

    stale = await client.post(
        "/api/v1/duels/802/boost-intent",
        headers=headers,
        json={
            "amount_nano": 500_000_000,
            "expected_revision": 1,
            "min_chance_bps": 6_000,
        },
    )
    assert stale.status_code == 409
    over_cap = await client.post(
        "/api/v1/duels/802/boost-intent",
        headers=headers,
        json={
            "amount_nano": 10_000_000_000,
            "expected_revision": 0,
            "min_chance_bps": 9_000,
        },
    )
    assert over_cap.status_code == 422


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

        async def get_contract_admin_state(self, mode: str, address: str) -> ContractAdminState:
            del mode, address
            return ContractAdminState(
                owner="0:" + "1" * 64,
                treasury="0:" + "1" * 64,
                fee_bps=1000,
                paused=False,
                locked_nano=0,
                extended_controls=True,
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


@pytest.mark.asyncio
async def test_holder_quote_issues_a_verifiable_fee_permit(client, app, monkeypatch) -> None:
    monkeypatch.setenv("LOOP_DUEL_HOLDER_FEE_ENABLED", "true")
    get_settings.cache_clear()

    class HolderPlushClient:
        async def verified_jetton_balance(self, owner_address: str, jetton_master: str) -> int:
            del owner_address, jetton_master
            return 1

    app.state.plush_ton_client = HolderPlushClient()
    headers = await authenticate(client)
    wallet = await add_wallet(app, 777000111)
    quote = await client.post(
        "/api/v1/duels/offers/quote",
        headers=headers,
        json={
            "offer_id": 54321,
            "chance_bps": 5000,
            "stake_nano": 1_000_000_000,
            "commitment_hex": "cd" * 32,
            "mode": "afk",
        },
    )
    assert quote.status_code == 201, quote.text
    result = quote.json()
    # The winner-if-won payout equals the pool: no protocol fee for holders.
    assert result["offer"]["fee_exempt"] is True
    assert result["offer"]["payout_nano"] == result["offer"]["total_pool_nano"]
    tx = result["transaction"]
    assert tx["holder_fee_supported"] is True
    assert tx["holder_valid_until"] > 0
    settings = get_settings()
    assert verify_holder_fee_permit(
        settings.duel_invite_public_key,
        tx["holder_signature_hex"],
        network=-3,
        contract_address=tx["contract_address"],
        offer_id=54321,
        owner_address=wallet.address,
        valid_until=tx["holder_valid_until"],
    )


@pytest.mark.asyncio
async def test_non_holder_quote_keeps_the_fee_and_issues_no_permit(
    client, app, monkeypatch
) -> None:
    monkeypatch.setenv("LOOP_DUEL_HOLDER_FEE_ENABLED", "true")
    get_settings.cache_clear()

    class EmptyPlushClient:
        async def verified_jetton_balance(self, owner_address: str, jetton_master: str) -> int:
            del owner_address, jetton_master
            return 0

    app.state.plush_ton_client = EmptyPlushClient()
    headers = await authenticate(client)
    await add_wallet(app, 777000111)
    quote = await client.post(
        "/api/v1/duels/offers/quote",
        headers=headers,
        json={
            "offer_id": 54322,
            "chance_bps": 5000,
            "stake_nano": 1_000_000_000,
            "commitment_hex": "ce" * 32,
            "mode": "afk",
        },
    )
    assert quote.status_code == 201, quote.text
    result = quote.json()
    assert result["offer"]["fee_exempt"] is False
    assert result["offer"]["payout_nano"] == 1_800_000_000
    tx = result["transaction"]
    # The wire layout flag still tells the client to emit the v1.4 maybe-bit.
    assert tx["holder_fee_supported"] is True
    assert tx["holder_signature_hex"] is None


@pytest.mark.asyncio
async def test_disabled_holder_fee_never_promises_a_discount(client, app) -> None:
    headers = await authenticate(client)
    await add_wallet(app, 777000111)
    quote = await client.post(
        "/api/v1/duels/offers/quote",
        headers=headers,
        json={
            "offer_id": 54323,
            "chance_bps": 5000,
            "stake_nano": 1_000_000_000,
            "commitment_hex": "cf" * 32,
            "mode": "afk",
        },
    )
    assert quote.status_code == 201, quote.text
    result = quote.json()
    assert result["offer"]["fee_exempt"] is False
    tx = result["transaction"]
    assert tx["holder_fee_supported"] is False
    assert tx["holder_signature_hex"] is None


@pytest.mark.asyncio
async def test_wire_layout_follows_the_contract_not_the_feature_flag(client, app) -> None:
    # Disabling the exemption must not change the open-message layout: the
    # deployed contract still expects the trailing maybe-bit, and emitting the
    # old body against it aborts every DUEL open while the API looks healthy.
    app.state.duel_holder_fee_supported = True
    headers = await authenticate(client)
    await add_wallet(app, 777000111)
    quote = await client.post(
        "/api/v1/duels/offers/quote",
        headers=headers,
        json={
            "offer_id": 54324,
            "chance_bps": 5000,
            "stake_nano": 1_000_000_000,
            "commitment_hex": "da" * 32,
            "mode": "afk",
        },
    )
    assert quote.status_code == 201, quote.text
    transaction = quote.json()["transaction"]
    assert transaction["holder_fee_supported"] is True
    assert transaction["holder_signature_hex"] is None
    assert quote.json()["offer"]["fee_exempt"] is False


@pytest.mark.asyncio
async def test_a_position_left_on_a_retired_contract_frees_the_wallet(client, app) -> None:
    """Switching BANK contracts must not lock every wallet out of the new one.

    A position on a contract the application has moved away from never settles
    — that contract is paused and its queue cannot advance. Held against the
    wallet, it blocked the owner from ever opening a position again, and the
    database constraint fired after the route's own check had passed, so the
    tester saw a bare connection error rather than any explanation.
    """
    from app.modules.bank.models import BankPosition, BankPositionStatus

    headers = await authenticate(client)
    wallet = await add_wallet(app, 777000111)
    settings = get_settings()
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == 777000111))
        assert user is not None
        db.add(
            BankPosition(
                position_id=8801,
                query_id=8801,
                user_id=user.id,
                wallet_id=wallet.id,
                owner_wallet=wallet.address,
                network=settings.ton_network_id,
                contract_address="0:" + "9" * 64,
                principal_nano=1_000_000_000,
                multiplier_bps=12_500,
                target_payout_nano=1_250_000_000,
                remaining_amount_nano=1_250_000_000,
                current_status=BankPositionStatus.PARTIALLY_FUNDED.value,
            )
        )
        await db.commit()

    quote = await client.post(
        "/api/v1/bank/positions/quote",
        headers=headers,
        json={"position_id": 8802, "principal_nano": 1_000_000_000, "multiplier_bps": 12_500},
    )
    assert quote.status_code == 201, quote.text

    # The rule still holds on the contract the application is actually on.
    again = await client.post(
        "/api/v1/bank/positions/quote",
        headers=headers,
        json={"position_id": 8803, "principal_nano": 1_000_000_000, "multiplier_bps": 12_500},
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_queue_size_counts_only_the_contract_people_can_join(client, app) -> None:
    """"В очереди" must mean the live queue.

    Positions stranded on a retired contract were counted too, so the app
    advertised a queue of three on a contract nobody could reach.
    """
    from app.modules.bank.models import BankPosition, BankPositionStatus

    headers = await authenticate(client)
    wallet = await add_wallet(app, 777000111)
    settings = get_settings()
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == 777000111))
        assert user is not None
        db.add(
            BankPosition(
                position_id=8901,
                query_id=8901,
                user_id=user.id,
                wallet_id=wallet.id,
                owner_wallet=wallet.address,
                network=settings.ton_network_id,
                contract_address="0:" + "9" * 64,
                principal_nano=1_000_000_000,
                multiplier_bps=12_500,
                target_payout_nano=1_250_000_000,
                remaining_amount_nano=1_250_000_000,
                current_status=BankPositionStatus.QUEUED.value,
            )
        )
        await db.commit()

    rating = await client.get("/api/v1/rating", headers=headers)
    assert rating.status_code == 200, rating.text
    assert rating.json()["pulse"]["active_bank"] == 0


@pytest.mark.asyncio
async def test_prelaunch_ranks_inviters_and_accrues_nothing_for_zero(client, app) -> None:
    """The waiting screen's race: counted by invitations, ranked honestly."""
    inviter_headers = await authenticate(client)
    async with app.state.session_factory() as db:
        inviter = await db.scalar(select(User).where(User.telegram_id == 777000111))
        assert inviter is not None
        from app.referrals import get_or_create_referral_code

        code = (await get_or_create_referral_code(db, inviter.id)).code
        await db.commit()

    # Two people arrive through the link, a third arrives on their own.
    for invitee_id in (555_100, 555_101):
        response = await client.post(
            "/api/v1/auth/telegram",
            json={"init_data": signed_init_data(invitee_id, start_param=f"ref_{code}")},
        )
        assert response.status_code == 200, response.text
    await client.post(
        "/api/v1/auth/telegram", json={"init_data": signed_init_data(555_102)}
    )

    view = (await client.get("/api/v1/prelaunch", headers=inviter_headers)).json()
    assert view["invited"] == 2
    assert view["rank"] == 1
    assert view["participants"] == 4
    top = view["leaderboard"][0]
    assert top["is_me"] is True and top["invited"] == 2

    # Somebody who invited nobody is unranked rather than tied for first.
    other = await authenticate(client, 555_102)
    other_view = (await client.get("/api/v1/prelaunch", headers=other)).json()
    assert other_view["rank"] is None
    assert other_view["invited"] == 0


@pytest.mark.asyncio
async def test_invite_card_is_public_and_keyed_by_referral_code(client, app, monkeypatch) -> None:
    """Telegram fetches the card unauthenticated; a stranger learns only a name."""
    from app.config import get_settings

    monkeypatch.setenv("LOOP_LAUNCH_AT", "2026-08-05T16:30:00Z")
    get_settings.cache_clear()

    headers = await authenticate(client)
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == 777000111))
        assert user is not None
        from app.referrals import get_or_create_referral_code

        code = (await get_or_create_referral_code(db, user.id)).code
        await db.commit()

    image = await client.get(f"/api/v1/prelaunch/cards/{code}-0.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert image.content[:3] == b"\xff\xd8\xff"

    # Every variant renders, and the joke actually differs between them.
    from app.result_cards import INVITE_VARIANTS

    other = await client.get(f"/api/v1/prelaunch/cards/{code}-1.jpg")
    assert other.status_code == 200
    assert other.content != image.content
    assert len({variant["headline"] for variant in INVITE_VARIANTS}) == len(INVITE_VARIANTS)

    assert (await client.get("/api/v1/prelaunch/cards/nope0000-0.jpg")).status_code == 404
    assert (await client.get(f"/api/v1/prelaunch/cards/{code}.jpg")).status_code == 404

    # Without a bot the share degrades loudly, not silently.
    denied = await client.post("/api/v1/prelaunch/share", headers=headers)
    assert denied.status_code == 503

    monkeypatch.delenv("LOOP_LAUNCH_AT", raising=False)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_duel_stake_bounds_follow_the_pool_cap(client, app, monkeypatch) -> None:
    """The interface must never offer a stake the contract cap forbids.

    With the launch cap the pool bounds meet, so exactly one stake is possible —
    and the field that offered a round 1 GRAM produced a rejected quote every
    time. Both ends now come from the same place the check does.
    """
    from app.config import get_settings

    headers = await authenticate(client)
    await add_wallet(app, 777000111)

    # Production runs the launch cap, where both ends of the pool meet.
    monkeypatch.setenv("LOOP_MAX_POOL_NANO", "1000000000")
    get_settings.cache_clear()
    limits = (await client.get("/api/v1/me", headers=headers)).json()["duel_stake"]
    assert limits == {"min_stake_nano": 500_000_000, "max_stake_nano": 500_000_000}

    denied = await client.post(
        "/api/v1/duels/offers/quote",
        headers=headers,
        json={
            "offer_id": 9101,
            "stake_nano": 1_000_000_000,
            "chance_bps": 5_000,
            "commitment_hex": "ab" * 32,
        },
    )
    assert denied.status_code == 422
    assert denied.json()["detail"] == "Сейчас ставка — ровно 0,5 GRAM"

    # Raising the cap widens both the published bounds and the refusal.
    monkeypatch.setenv("LOOP_MAX_POOL_NANO", "10000000000")
    get_settings.cache_clear()
    widened = (await client.get("/api/v1/me", headers=headers)).json()["duel_stake"]
    assert widened == {"min_stake_nano": 500_000_000, "max_stake_nano": 5_000_000_000}
    too_big = await client.post(
        "/api/v1/duels/offers/quote",
        headers=headers,
        json={
            "offer_id": 9102,
            "stake_nano": 9_000_000_000,
            "chance_bps": 5_000,
            "commitment_hex": "cd" * 32,
        },
    )
    assert too_big.json()["detail"] == "Ставка должна быть от 0,5 до 5 GRAM"

    monkeypatch.delenv("LOOP_MAX_POOL_NANO", raising=False)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_a_refused_signature_frees_the_wallet_immediately(client, app) -> None:
    """Declining in the wallet must cost nothing, including the next fifteen minutes.

    A quote reserves the wallet's single offer slot before the wallet is even
    opened. Left behind, it showed the player a search for a duel that does not
    exist and refused every attempt to start another.
    """
    headers = await authenticate(client)
    await add_wallet(app, 777000111)
    body = {
        "offer_id": 31337,
        "chance_bps": 5000,
        "stake_nano": 1_000_000_000,
        "commitment_hex": "ab" * 32,
        "mode": "afk",
    }
    assert (
        await client.post("/api/v1/duels/offers/quote", headers=headers, json=body)
    ).status_code == 201

    # The slot is taken while the wallet is being asked.
    blocked = await client.post(
        "/api/v1/duels/offers/quote", headers=headers, json={**body, "offer_id": 31338}
    )
    assert blocked.status_code == 409

    discarded = await client.post("/api/v1/duels/offers/31337/discard", headers=headers)
    assert discarded.status_code == 204
    # History keeps the row; what matters is that nothing is active any more,
    # which is exactly the set the interface treats as a live duel.
    listed = (await client.get("/api/v1/duels/offers", headers=headers)).json()
    assert [offer["state"] for offer in listed] == ["expired"]
    active = {"pending_funding", "open", "reserved", "matched"}
    assert not [offer for offer in listed if offer["state"] in active]

    # And the player can start again at once.
    again = await client.post(
        "/api/v1/duels/offers/quote", headers=headers, json={**body, "offer_id": 31339}
    )
    assert again.status_code == 201

    # What the chain has seen is not a button's to undo.
    async with app.state.session_factory() as db:
        from app.modules.duel.models import DuelOffer

        offer = await db.scalar(select(DuelOffer).where(DuelOffer.onchain_offer_id == 31339))
        assert offer is not None
        offer.funding_tx_hash = "ab" * 32
        await db.commit()
    funded = await client.post("/api/v1/duels/offers/31339/discard", headers=headers)
    assert funded.status_code == 409


@pytest.mark.asyncio
async def test_a_paused_duel_contract_is_never_offered_for_signature(client, app) -> None:
    """A paused contract rejects every deposit and bounces the stake back.

    Quoting one builds a transaction that cannot succeed, so the refusal has to
    happen before a wallet is ever opened — and a contract we cannot ask counts
    as closed, not as open.
    """
    from app.ton import ContractAdminState, TonProviderError

    headers = await authenticate(client)
    await add_wallet(app, 777000111)
    body = {
        "offer_id": 41000,
        "chance_bps": 5000,
        "stake_nano": 1_000_000_000,
        "commitment_hex": "ab" * 32,
        "mode": "afk",
    }

    class PausedTonClient:
        async def get_contract_admin_state(self, mode: str, address: str) -> ContractAdminState:
            del mode, address
            return ContractAdminState(
                owner="0:" + "1" * 64,
                treasury="0:" + "1" * 64,
                fee_bps=1000,
                paused=True,
                locked_nano=0,
                extended_controls=True,
            )

    class UnreachableTonClient:
        async def get_contract_admin_state(self, mode: str, address: str) -> ContractAdminState:
            raise TonProviderError("provider is down")

    app.state.ton_client = PausedTonClient()
    paused = await client.post("/api/v1/duels/offers/quote", headers=headers, json=body)
    assert paused.status_code == 409
    assert paused.json()["detail"] == "DUEL сейчас закрыт"

    app.state.ton_client = UnreachableTonClient()
    unknown = await client.post("/api/v1/duels/offers/quote", headers=headers, json=body)
    assert unknown.status_code == 503

    # Nothing was reserved by either refusal.
    assert (await client.get("/api/v1/duels/offers", headers=headers)).json() == []


@pytest.mark.asyncio
async def test_a_paused_bank_is_never_offered_for_signature(client, app) -> None:
    """Pausing BANK is routine — the panel demands it to change fee or withdraw.

    Every deposit signed meanwhile bounces with exit code 101, so the refusal
    has to happen before a wallet opens, and an unreachable contract counts as
    closed rather than open.
    """
    from app.ton import ContractAdminState, TonProviderError

    headers = await authenticate(client)
    await add_wallet(app, 777000111)
    body = {"position_id": 51000, "principal_nano": 1_000_000_000, "multiplier_bps": 12_500}

    class PausedTonClient:
        async def get_contract_admin_state(self, mode: str, address: str) -> ContractAdminState:
            del mode, address
            return ContractAdminState(
                owner="0:" + "1" * 64,
                treasury="0:" + "1" * 64,
                fee_bps=1000,
                paused=True,
                locked_nano=0,
                extended_controls=True,
            )

    class UnreachableTonClient:
        async def get_contract_admin_state(self, mode: str, address: str) -> ContractAdminState:
            raise TonProviderError("provider is down")

    app.state.ton_client = PausedTonClient()
    paused = await client.post("/api/v1/bank/positions/quote", headers=headers, json=body)
    assert paused.status_code == 409
    assert paused.json()["detail"] == "BANK сейчас закрыт"

    app.state.ton_client = UnreachableTonClient()
    assert (
        await client.post("/api/v1/bank/positions/quote", headers=headers, json=body)
    ).status_code == 503

    assert (await client.get("/api/v1/bank/positions", headers=headers)).json() == []


@pytest.mark.asyncio
async def test_a_refused_bank_signature_frees_the_slot_at_once(client, app) -> None:
    """Declining in the wallet must not cost the next six minutes."""
    headers = await authenticate(client)
    await add_wallet(app, 777000111)
    body = {"position_id": 52000, "principal_nano": 1_000_000_000, "multiplier_bps": 12_500}

    assert (
        await client.post("/api/v1/bank/positions/quote", headers=headers, json=body)
    ).status_code == 201
    blocked = await client.post(
        "/api/v1/bank/positions/quote", headers=headers, json={**body, "position_id": 52001}
    )
    assert blocked.status_code == 409

    discarded = await client.post("/api/v1/bank/positions/52000/discard", headers=headers)
    assert discarded.status_code == 204

    again = await client.post(
        "/api/v1/bank/positions/quote", headers=headers, json={**body, "position_id": 52002}
    )
    assert again.status_code == 201

    # What the chain has seen is not a button's to undo.
    async with app.state.session_factory() as db:
        from app.modules.bank.models import BankPosition

        position = await db.scalar(select(BankPosition).where(BankPosition.position_id == 52002))
        assert position is not None
        position.funding_transaction = "ab" * 32
        await db.commit()
    funded = await client.post("/api/v1/bank/positions/52002/discard", headers=headers)
    assert funded.status_code == 409


@pytest.mark.asyncio
async def test_the_jar_shows_the_queue_coming_towards_you_not_a_flat_zero(client, app) -> None:
    # A deposit fills the head to the brim before a single nanogram reaches the
    # position behind it. Shown as one's own fill, ninety-eight people watched a
    # jar frozen at zero on opening night — accurate and worthless. What moves
    # for all of them, on every deposit anybody makes, is the distance from the
    # head, and that is what the jar must show until their own turn arrives.
    from app.modules.bank.models import BankPosition, BankPositionStatus

    telegram_id = 777000222
    settings = get_settings()
    headers = await authenticate(client, telegram_id)
    wallet = await add_wallet(app, telegram_id)
    opened_at = datetime.now(UTC) - timedelta(hours=2)

    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
        assert user is not None
        common = {
            "network": settings.ton_network_id,
            "contract_address": settings.bank_contract_address,
            "principal_nano": 1_000_000_000,
            "multiplier_bps": 20_000,
            "target_payout_nano": 2_000_000_000,
        }
        # Ten positions were already paid before this one opened, four of them
        # only afterwards — so ten stood ahead at the time, six stand there now.
        for index in range(14):
            db.add(
                BankPosition(
                    position_id=5_000 + index,
                    query_id=5_000 + index,
                    owner_wallet="0:" + f"{index:02x}" * 32,
                    funded_amount_nano=2_000_000_000,
                    remaining_amount_nano=0,
                    queue_index=index,
                    created_at=opened_at - timedelta(minutes=10),
                    current_status=BankPositionStatus.PAYOUT_SENT.value,
                    completed_at=(
                        opened_at - timedelta(minutes=1)
                        if index < 10
                        else datetime.now(UTC) - timedelta(minutes=1)
                    ),
                    **common,
                )
            )
        # Two positions still waiting in front, each needing a whole GRAM more.
        for index in (14, 15):
            db.add(
                BankPosition(
                    position_id=5_000 + index,
                    query_id=5_000 + index,
                    owner_wallet="0:" + f"{index:02x}" * 32,
                    funded_amount_nano=1_000_000_000,
                    remaining_amount_nano=1_000_000_000,
                    queue_index=index,
                    created_at=opened_at - timedelta(minutes=5),
                    current_status=BankPositionStatus.QUEUED.value,
                    **common,
                )
            )
        db.add(
            BankPosition(
                position_id=5_016,
                query_id=5_016,
                user_id=user.id,
                wallet_id=wallet.id,
                owner_wallet=wallet.address,
                funded_amount_nano=0,
                remaining_amount_nano=2_000_000_000,
                queue_index=16,
                created_at=opened_at,
                current_status=BankPositionStatus.QUEUED.value,
                **common,
            )
        )
        for index in (17, 18, 19):
            db.add(
                BankPosition(
                    position_id=5_000 + index,
                    query_id=5_000 + index,
                    owner_wallet="0:" + f"{index:02x}" * 32,
                    funded_amount_nano=0,
                    remaining_amount_nano=2_000_000_000,
                    queue_index=index,
                    current_status=BankPositionStatus.QUEUED.value,
                    **common,
                )
            )
        await db.commit()

    body = (await client.get("/api/v1/bank/positions/current", headers=headers)).json()

    # Nothing has reached it yet, and the old jar would have shown exactly this.
    assert body["funded_amount_nano"] == 0
    assert body["progress_bps"] == 0

    # Two positions still stand in front needing a GRAM each, and this one is
    # owed two: four GRAM must still arrive. Three GRAM was deposited after it
    # opened and nine tenths of that reached the queue, so the journey stands at
    # 2.7 of 6.7 — moving, while the position itself is still funded by nothing.
    assert body["queue_ahead"] == 2
    assert body["queue_ahead_nano"] == 2_000_000_000
    assert body["queue_progress_bps"] == 4_029


@pytest.mark.asyncio
async def test_an_announcement_reaches_only_the_audience_it_names(client) -> None:
    # Two thirds of the audience never pressed Start, so Telegram forbids the
    # bot from writing to them and the app is the only way to say anything.
    # That reach is exactly why widening it must be deliberate: silence is the
    # default in both directions, and "everybody" has to be typed out.
    settings = get_settings()
    headers = await authenticate(client, 777000333)
    profile = await client.get("/api/v1/me", headers=headers)
    assert profile.json()["announcement"] is None

    settings.announcement_text = "Первая ночь. 575 GRAM отправлено людям."
    settings.announcement_url = "https://t.me/rubikub/5158"

    # Text alone changes nothing while no audience is named.
    assert (await client.get("/api/v1/me", headers=headers)).json()["announcement"] is None

    settings.announcement_telegram_ids = "1084693264"
    assert (await client.get("/api/v1/me", headers=headers)).json()["announcement"] is None

    settings.announcement_telegram_ids = "1084693264, 777000333"
    shown = (await client.get("/api/v1/me", headers=headers)).json()["announcement"]
    assert shown == {
        "text": "Первая ночь. 575 GRAM отправлено людям.",
        "url": "https://t.me/rubikub/5158",
    }

    settings.announcement_telegram_ids = "*"
    assert (await client.get("/api/v1/me", headers=headers)).json()["announcement"] is not None

    # Emptying the text takes it down again without touching the audience.
    settings.announcement_text = ""
    assert (await client.get("/api/v1/me", headers=headers)).json()["announcement"] is None
    settings.announcement_telegram_ids = ""
    settings.announcement_url = ""


@pytest.mark.asyncio
async def test_a_quiet_night_produces_no_estimate_rather_than_days(client, app) -> None:
    # The first night showed how a one-hour window fails: almost nothing arrives,
    # a small number divides into a very large one, and the screen starts
    # promising days. Past a working day the honest answer is how much has to
    # arrive and nothing at all about when.
    from app.modules.bank.models import BankPosition, BankPositionStatus

    telegram_id = 777000444
    settings = get_settings()
    headers = await authenticate(client, telegram_id)
    wallet = await add_wallet(app, telegram_id)

    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == telegram_id))
        common = {
            "network": settings.ton_network_id,
            "contract_address": settings.bank_contract_address,
            "principal_nano": 1_000_000_000,
            "multiplier_bps": 20_000,
            "target_payout_nano": 2_000_000_000,
        }
        # A hundred GRAM owed in front, and one lonely deposit all night.
        db.add(
            BankPosition(
                position_id=6_001,
                query_id=6_001,
                owner_wallet="0:" + "aa" * 32,
                funded_amount_nano=0,
                remaining_amount_nano=100_000_000_000,
                target_payout_nano=100_000_000_000,
                queue_index=0,
                created_at=datetime.now(UTC) - timedelta(hours=8),
                current_status=BankPositionStatus.QUEUED.value,
                **{key: value for key, value in common.items() if key != "target_payout_nano"},
            )
        )
        db.add(
            BankPosition(
                position_id=6_002,
                query_id=6_002,
                user_id=user.id,
                wallet_id=wallet.id,
                owner_wallet=wallet.address,
                funded_amount_nano=0,
                remaining_amount_nano=2_000_000_000,
                queue_index=1,
                created_at=datetime.now(UTC) - timedelta(hours=7),
                current_status=BankPositionStatus.QUEUED.value,
                **common,
            )
        )
        await db.commit()

    body = (await client.get("/api/v1/bank/positions/current", headers=headers)).json()

    assert body["queue_ahead"] == 1
    assert body["queue_ahead_nano"] == 100_000_000_000
    # It still says how far off it is; it refuses to say when.
    assert body["queue_eta_seconds"] is None


@pytest.mark.asyncio
async def test_a_provider_timeout_does_not_erase_a_confirmed_holder(client, app) -> None:
    # Every open client polls /me every few seconds, and each poll used to ask
    # the indexer afresh. Past a handful of users that is a rate limit, and the
    # failure silently flipped holder to false: a player whose duels genuinely
    # settle fee-free watched the screen claim 10% off them. Ownership of a
    # token does not vanish with a timeout.
    from app.routes import PLUSH_HOLDER_CACHE_TTL
    from app.ton import JettonWalletState, TonProviderError

    calls = {"count": 0}

    class FlakyPlushClient:
        async def get_jetton_wallet(self, owner_address: str, jetton_master: str):
            del owner_address, jetton_master
            calls["count"] += 1
            if calls["count"] > 1:
                raise TonProviderError("rate limited")
            return JettonWalletState(
                owner_address="0:" + "5" * 64,
                jetton_master="master",
                wallet_address="0:" + "e" * 64,
                balance_nano=10_054_226_191,
            )

    app.state.plush_ton_client = FlakyPlushClient()
    app.state.plush_holder_cache = {}
    headers = await authenticate(client, 777000555)
    await add_wallet(app, 777000555, byte="5")

    first = (await client.get("/api/v1/me", headers=headers)).json()
    assert first["plush_brick"]["holder"] is True

    # Within the TTL the cache answers and the indexer is left alone.
    second = (await client.get("/api/v1/me", headers=headers)).json()
    assert second["plush_brick"]["holder"] is True
    assert calls["count"] == 1

    # Past the TTL the refresh fails — and the last confirmed answer stands.
    for entry in list(app.state.plush_holder_cache):
        stamp, balance = app.state.plush_holder_cache[entry]
        app.state.plush_holder_cache[entry] = (stamp - PLUSH_HOLDER_CACHE_TTL - 1, balance)
    third = (await client.get("/api/v1/me", headers=headers)).json()
    assert calls["count"] == 2
    assert third["plush_brick"]["holder"] is True
    assert third["plush_brick"]["balance_nano"] == 10_054_226_191


@pytest.mark.asyncio
async def test_the_weekly_race_ranks_money_and_forgets_last_week(client, app) -> None:
    # Registrations were farmable — 22 bots took first place in the prelaunch
    # race in under three minutes. GRAM earned from invitees' real deposits is
    # the one number a farm cannot fake, and a week that never resets would
    # crown the same names forever.
    from app.models import ReferralAttribution, ReferralCode, ReferralReward
    from app.rating import race_week_window

    week_start, _ = race_week_window()
    headers = await authenticate(client, 777000666)

    async with app.state.session_factory() as db:
        me = await db.scalar(select(User).where(User.telegram_id == 777000666))
        rival = User(telegram_id=777000667, first_name="Соперница", username="rivalka")
        sleeper = User(telegram_id=777000668, first_name="Прошлая неделя")
        invitee_a = User(telegram_id=777000669, first_name="Гость А")
        invitee_b = User(telegram_id=777000670, first_name="Гость Б")
        invitee_c = User(telegram_id=777000671, first_name="Гость В")
        db.add_all([rival, sleeper, invitee_a, invitee_b, invitee_c])
        await db.flush()
        db.add_all(
            [
                ReferralCode(code="race-me", owner_user_id=me.id),
                ReferralCode(code="race-rival", owner_user_id=rival.id),
                ReferralCode(code="race-sleeper", owner_user_id=sleeper.id),
            ]
        )
        await db.flush()
        rows = [
            (me, invitee_a, "race-me", 40_000_000, week_start + timedelta(hours=1)),
            (rival, invitee_b, "race-rival", 100_000_000, week_start + timedelta(hours=2)),
            # Real money, wrong week: must not appear in this race at all.
            (sleeper, invitee_c, "race-sleeper", 900_000_000, week_start - timedelta(days=1)),
        ]
        for inviter, invitee, code, nano, moment in rows:
            attribution = ReferralAttribution(
                inviter_user_id=inviter.id,
                invitee_user_id=invitee.id,
                code=code,
                created_at=moment,
            )
            db.add(attribution)
            await db.flush()
            db.add(
                ReferralReward(
                    attribution_id=attribution.id,
                    cause=f"fee_share:test-{code}",
                    reward_nano=nano,
                    reward_points=0,
                    created_at=moment,
                )
            )
        await db.commit()

    rating = (await client.get("/api/v1/rating", headers=headers)).json()
    race = rating["invite_race"]

    assert [entry["first_name"] for entry in race] == ["Соперница", "Loop"]
    assert race[0]["earned_nano"] == 100_000_000
    assert race[0]["rank"] == 1
    assert race[1]["is_me"] is True
    assert rating["invite_race_me"]["rank"] == 2
    assert rating["invite_race_me"]["earned_nano"] == 40_000_000
    # Last week's hero is nowhere in this week's table.
    assert all(entry["first_name"] != "Прошлая неделя" for entry in race)
    assert rating["invite_race_ends_at"] is not None


@pytest.mark.asyncio
async def test_a_duel_card_names_the_loser_and_says_so_out_loud(client, app) -> None:
    # Winning a duel against a person and being handed an anonymous receipt is
    # the flattest possible version of the moment. The owner asked for teeth:
    # the card names who lost, and the caption taunts them by @username.
    from app.models import ResultCard
    from app.modules.duel.models import Duel, DuelOffer, DuelState, OfferState
    from app.result_cards import duel_opponent_label, result_caption

    settings = get_settings()
    winner_headers = await authenticate(client, 777000777)
    await authenticate(client, 777000778)

    async with app.state.session_factory() as db:
        winner = await db.scalar(select(User).where(User.telegram_id == 777000777))
        loser = await db.scalar(select(User).where(User.telegram_id == 777000778))
        loser.username = "iloveflopp"
        offers = []
        for index, person in enumerate((winner, loser)):
            offer = DuelOffer(
                onchain_offer_id=880_001 + index,
                query_id=880_001 + index,
                user_id=person.id,
                owner_wallet="0:" + f"{index:02x}" * 32,
                network=settings.ton_network_id,
                contract_address="0:" + "ab" * 32,
                chance_bps=5_000,
                total_pool_nano=2_000_000_000,
                stake_nano=1_000_000_000,
                opponent_stake_nano=1_000_000_000,
                fee_bps=1_000,
                payout_nano=1_800_000_000,
                commitment_hex="cd" * 32,
                mode="afk",
                state=OfferState.SETTLED.value,
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
            db.add(offer)
            offers.append(offer)
        await db.flush()
        duel = Duel(
            onchain_duel_id=880_100,
            network=settings.ton_network_id,
            offer_a_id=offers[0].id,
            offer_b_id=offers[1].id,
            state=DuelState.SETTLED.value,
            boost_revision=0,
            reveal_deadline=datetime.now(UTC) + timedelta(minutes=5),
        )
        db.add(duel)
        await db.flush()
        card = ResultCard(
            user_id=winner.id,
            mode="duel",
            entity_id=duel.id,
            event_key="duel:test:880100",
            network=settings.ton_network_id,
            payout_nano=1_800_000_000,
            contributed_nano=1_000_000_000,
            result_nano=800_000_000,
            tx_hash="hash-880100",
            proof_url="https://tonviewer.com/transaction/hash-880100",
        )
        db.add(card)
        await db.commit()

        label = await duel_opponent_label(db, card)
        assert label == "@iloveflopp"
        caption = result_caption(card, label)
        assert "@iloveflopp" in caption
        # Never the flat anonymous line once the loser is known.
        assert "Я забрал DUEL в LOOP." not in caption
        public_id = card.public_id

    image = await client.get(f"/api/v1/results/cards/{public_id}.jpg")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/jpeg"
    assert winner_headers


@pytest.mark.asyncio
async def test_the_biggest_positions_may_not_aim_for_double(client, app) -> None:
    # The ceiling rose to ten GRAM; the doubling target did not follow it up.
    # A ten-GRAM position aiming at x2 asks the queue for roughly 22 GRAM of
    # future deposits to close, against 16.7 at x1.5 — and 109 of the 118 open
    # positions were already sitting at x2 when this shipped. The threshold is
    # exercised below the ladder's own limit so this tests the rule, not the
    # rung a fresh queue happens to be standing on.
    settings = get_settings()
    settings.bank_double_limit_nano = GRAM // 2
    headers = await authenticate(client, 777000888)
    await add_wallet(app, 777000888, byte="8")

    limits = (await client.get("/api/v1/bank/limits", headers=headers)).json()
    assert limits["double_limit_nano"] == GRAM // 2

    over = await client.post(
        "/api/v1/bank/positions/preview",
        headers=headers,
        json={"principal_nano": GRAM, "multiplier_bps": 20_000},
    )
    assert over.status_code == 422
    assert "×2" in over.json()["detail"]

    gentler = await client.post(
        "/api/v1/bank/positions/preview",
        headers=headers,
        json={"principal_nano": GRAM, "multiplier_bps": 15_000},
    )
    assert gentler.status_code == 200, gentler.text
    assert gentler.json()["target_payout_nano"] == GRAM * 15_000 // 10_000

    # Exactly at the line is still allowed: the rule bites above it, not on it.
    settings.bank_double_limit_nano = GRAM
    at_the_line = await client.post(
        "/api/v1/bank/positions/preview",
        headers=headers,
        json={"principal_nano": GRAM, "multiplier_bps": 20_000},
    )
    assert at_the_line.status_code == 200, at_the_line.text
    settings.bank_double_limit_nano = 5 * GRAM


@pytest.mark.asyncio
async def test_a_referral_payout_can_be_asked_for_once_and_is_fixed_when_asked(
    client, app
) -> None:
    # People earned, watched the figure grow, and had nowhere to say "send it
    # here" except the chat. Paying stays manual; asking should not be. The
    # amount is frozen at the moment of asking so later accruals cannot
    # silently change what was agreed, and a second open request would ask for
    # the same money twice.
    from app.models import (
        ReferralAttribution,
        ReferralCode,
        ReferralPayoutRequest,
        ReferralReward,
    )

    settings = get_settings()
    settings.referral_min_payout_nano = 500_000_000
    headers = await authenticate(client, 777000999)
    wallet_address = "UQD8H0kPp7Y0AT-wDHAzyG8wiWPy6-KxIBcExD_WId_okeHK"

    async with app.state.session_factory() as db:
        me = await db.scalar(select(User).where(User.telegram_id == 777000999))
        invitee = User(telegram_id=777001000, first_name="Гость")
        db.add(invitee)
        await db.flush()
        db.add(ReferralCode(code="payout-code", owner_user_id=me.id))
        attribution = ReferralAttribution(
            inviter_user_id=me.id, invitee_user_id=invitee.id, code="payout-code"
        )
        db.add(attribution)
        await db.flush()
        db.add_all(
            [
                ReferralReward(
                    attribution_id=attribution.id,
                    cause="fee_share:paid-one",
                    reward_nano=200_000_000,
                    payout_tx_hash="already-sent",
                ),
                ReferralReward(
                    attribution_id=attribution.id,
                    cause="fee_share:open-one",
                    reward_nano=900_000_000,
                ),
            ]
        )
        await db.commit()
        me_id = me.id

    before = (await client.get("/api/v1/referrals", headers=headers)).json()
    assert before["reward_nano"] == 1_100_000_000
    # What is left to send: everything accrued minus what already went out.
    assert before["available_nano"] == 900_000_000
    assert before["pending_payout"] is None

    refused = await client.post(
        "/api/v1/referrals/payout", headers=headers, json={"address": "not-an-address-at-all-x"}
    )
    assert refused.status_code == 422

    asked = await client.post(
        "/api/v1/referrals/payout", headers=headers, json={"address": wallet_address}
    )
    assert asked.status_code == 200, asked.text
    assert asked.json()["amount_nano"] == 900_000_000
    assert asked.json()["state"] == "requested"

    # Asking again while one is open would put the same money in the queue twice.
    again = await client.post(
        "/api/v1/referrals/payout", headers=headers, json={"address": wallet_address}
    )
    assert again.status_code == 409

    after = (await client.get("/api/v1/referrals", headers=headers)).json()
    assert after["pending_payout"]["amount_nano"] == 900_000_000
    # Nothing is left to ask for while the request stands.
    assert after["available_nano"] == 0

    async with app.state.session_factory() as db:
        stored = await db.scalar(
            select(ReferralPayoutRequest).where(ReferralPayoutRequest.user_id == me_id)
        )
        # Stored in raw form, so the treasury pays the same wallet either way.
        assert stored.address.startswith("0:")
        assert stored.amount_nano == 900_000_000


@pytest.mark.asyncio
async def test_dust_is_not_worth_a_transfer(client, app) -> None:
    from app.models import ReferralAttribution, ReferralCode, ReferralReward

    settings = get_settings()
    settings.referral_min_payout_nano = 500_000_000
    headers = await authenticate(client, 777001001)

    async with app.state.session_factory() as db:
        me = await db.scalar(select(User).where(User.telegram_id == 777001001))
        invitee = User(telegram_id=777001002, first_name="Гость")
        db.add(invitee)
        await db.flush()
        db.add(ReferralCode(code="dust-code", owner_user_id=me.id))
        attribution = ReferralAttribution(
            inviter_user_id=me.id, invitee_user_id=invitee.id, code="dust-code"
        )
        db.add(attribution)
        await db.flush()
        db.add(
            ReferralReward(
                attribution_id=attribution.id,
                cause="fee_share:dust",
                reward_nano=10_000_000,
            )
        )
        await db.commit()

    refused = await client.post(
        "/api/v1/referrals/payout",
        headers=headers,
        json={"address": "UQD8H0kPp7Y0AT-wDHAzyG8wiWPy6-KxIBcExD_WId_okeHK"},
    )
    assert refused.status_code == 422
    assert "0,5" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_the_owner_is_told_about_a_payout_request(client, app, monkeypatch) -> None:
    # The request is worth nothing if nobody sees it: paying is manual, so the
    # message in the owner's chat is the whole delivery mechanism.
    from app.models import ReferralAttribution, ReferralCode, ReferralReward

    settings = get_settings()
    settings.referral_min_payout_nano = 500_000_000
    settings.alert_chat_id = 1084693264
    headers = await authenticate(client, 777001003)

    async with app.state.session_factory() as db:
        me = await db.scalar(select(User).where(User.telegram_id == 777001003))
        me.username = "zovushiy"
        invitee = User(telegram_id=777001004, first_name="Гость")
        db.add(invitee)
        await db.flush()
        db.add(ReferralCode(code="alert-code", owner_user_id=me.id))
        attribution = ReferralAttribution(
            inviter_user_id=me.id, invitee_user_id=invitee.id, code="alert-code"
        )
        db.add(attribution)
        await db.flush()
        db.add(
            ReferralReward(
                attribution_id=attribution.id,
                cause="fee_share:alert",
                reward_nano=1_500_000_000,
            )
        )
        await db.commit()

    sent: list[tuple[int, str]] = []

    class FakeBot:
        async def send_message(self, chat_id: int, text: str) -> None:
            sent.append((chat_id, text))

    monkeypatch.setattr(app.state, "bot", FakeBot(), raising=False)

    asked = await client.post(
        "/api/v1/referrals/payout",
        headers=headers,
        json={"address": "UQD8H0kPp7Y0AT-wDHAzyG8wiWPy6-KxIBcExD_WId_okeHK"},
    )
    assert asked.status_code == 200, asked.text

    assert len(sent) == 1
    chat_id, text = sent[0]
    assert chat_id == 1084693264
    assert "@zovushiy" in text
    assert "1.500 GRAM" in text
    # The address is echoed in the form the person typed, to be checked by eye.
    assert "UQD8H0kPp7Y0AT-wDHAzyG8wiWPy6-KxIBcExD_WId_okeHK" in text
    settings.alert_chat_id = 0
