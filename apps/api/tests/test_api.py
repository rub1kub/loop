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
from app.ton import ContractState, JettonWalletState, verify_holder_fee_permit


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
