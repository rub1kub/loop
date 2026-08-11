import base64
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from tonsdk.boc import Cell  # type: ignore[import-untyped]

from app import control_routes
from app.config import get_settings
from app.control_state import application_control, ensure_mode_enabled
from app.security import issue_control_session
from app.ton import ContractAdminState, ContractState, TransactionProof

OWNER = "0:" + "22" * 32


class FakeControlTonClient:
    async def get_wallet_public_key(self, address: str) -> str:
        assert address == OWNER
        return "aa" * 32

    async def get_contract_state(self, address: str) -> ContractState:
        is_bank = address.endswith("12" * 32)
        return ContractState(
            address=address,
            status="active",
            balance_nano=3_000_000_000 if is_bank else 2_000_000_000,
            code_hash=("AA" if is_bank else "BB") * 32,
            last_transaction_hash="proof",
            last_transaction_lt=99,
        )

    async def get_contract_admin_state(self, mode: str, address: str) -> ContractAdminState:
        del address
        return ContractAdminState(
            owner=OWNER,
            treasury=OWNER,
            fee_bps=100 if mode == "bank" else 250,
            paused=mode == "duel",
            locked_nano=1_000_000_000,
            extended_controls=True,
        )

    async def verify_wallet_transfer(
        self,
        signed_boc: str,
        sender: str,
        destination: str,
        amount_nano: int,
        payload_boc: str,
    ) -> TransactionProof:
        assert signed_boc
        assert sender == OWNER
        assert destination.startswith("0:")
        assert amount_nano > 0
        assert payload_boc
        return TransactionProof(
            transaction_hash="ab" * 32,
            account=sender,
            logical_time=123,
            masterchain_seqno=456,
            confirmed_at=datetime.now(UTC),
        )


def authorize_control(client) -> None:
    token, _ = issue_control_session(OWNER, get_settings())
    client.cookies.set("loop_control", token, path="/api/v1/control")


@pytest.mark.asyncio
async def test_control_login_requires_one_time_owner_proof(client, app, monkeypatch) -> None:
    app.state.ton_client = FakeControlTonClient()
    challenge = await client.post("/api/v1/control/challenge", json={})
    assert challenge.status_code == 200
    payload = challenge.json()["payload"]
    monkeypatch.setattr(control_routes, "verify_ton_proof", lambda **_: OWNER)
    proof = {
        "address": OWNER,
        "network": -3,
        "publicKey": "aa" * 32,
        "proof": {
            "timestamp": 1_800_000_000,
            "domain": {"lengthBytes": 9, "value": "loop.test"},
            "signature": "A" * 88,
            "payload": payload,
        },
    }
    response = await client.post("/api/v1/control/session", json=proof)
    assert response.status_code == 200, response.text
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    replay = await client.post("/api/v1/control/session", json=proof)
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_control_overview_and_safe_transaction_preparation(client, app) -> None:
    app.state.ton_client = FakeControlTonClient()
    assert (await client.get("/api/v1/control/overview")).status_code == 401
    authorize_control(client)

    overview = await client.get("/api/v1/control/overview")
    assert overview.status_code == 200, overview.text
    contracts = {item["mode"]: item for item in overview.json()["contracts"]}
    assert contracts["bank"]["withdrawable_nano"] == 1_800_000_000
    assert contracts["duel"]["paused"] is True
    assert contracts["bank"]["owner_matches_session"] is True

    pause = await client.post(
        "/api/v1/control/transactions",
        json={"mode": "bank", "action": "pause", "paused": True},
    )
    assert pause.status_code == 200, pause.text
    cells = Cell.one_from_boc(base64.b64decode(pause.json()["payload"]))
    cell = cells[0] if isinstance(cells, list) else cells
    parser = cell.begin_parse()
    assert parser.read_uint(32) == 0x4C424E02
    assert parser.read_uint(64) == pause.json()["query_id"]
    assert parser.read_uint(1) == 1

    too_much = await client.post(
        "/api/v1/control/transactions",
        json={
            "mode": "duel",
            "action": "withdraw_surplus",
            "amount_nano": 900_000_000,
        },
    )
    assert too_much.status_code == 409
    missing_confirmation = await client.post(
        "/api/v1/control/transactions",
        json={"mode": "duel", "action": "set_owner", "address": "0:" + "44" * 32},
    )
    assert missing_confirmation.status_code == 422


@pytest.mark.asyncio
async def test_wave_position_is_prepared_only_for_the_configured_external_wallet(
    client, app, monkeypatch
) -> None:
    app.state.ton_client = FakeControlTonClient()
    authorize_control(client)
    settings = get_settings().model_copy(
        update={
            "bank_wave_enabled": True,
            "bank_wave_wallet": OWNER,
            "bank_wave_boost_nano": 5_000_000_000,
        }
    )
    app.dependency_overrides[get_settings] = lambda: settings

    async def ready_wave(*_args, **_kwargs):
        return SimpleNamespace(
            id="2026-08-16",
            state="goal_reached",
            boost_nano=5_000_000_000,
            boost_confirmed=False,
        )

    monkeypatch.setattr(control_routes, "bank_wave_view", ready_wave)
    try:
        response = await client.post("/api/v1/control/wave/transaction", json={})
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sender_address"] == OWNER
    assert int(body["amount_nano"]) == 5_000_000_000 + settings.bank_position_gas_nano
    cells = Cell.one_from_boc(base64.b64decode(body["payload"]))
    cell = cells[0] if isinstance(cells, list) else cells
    parser = cell.begin_parse()
    assert parser.read_uint(32) == 0x4C424E01
    assert parser.read_uint(64) == body["query_id"]
    assert parser.read_uint(64) == body["query_id"]
    assert parser.read_coins() == 5_000_000_000
    assert parser.read_uint(16) == 12_500


@pytest.mark.asyncio
async def test_application_pause_blocks_only_new_operations(client, app) -> None:
    # Switching the application off now asks the chain who owns the contract,
    # so this needs a chain to ask.
    app.state.ton_client = FakeControlTonClient()
    authorize_control(client)
    response = await client.patch(
        "/api/v1/control/application",
        json={"maintenance_enabled": True},
    )
    assert response.status_code == 200, response.text
    async with app.state.session_factory() as db:
        with pytest.raises(HTTPException) as error:
            await ensure_mode_enabled(db, "bank")
        assert error.value.status_code == 503
        control = await application_control(db)
        assert control.bank_enabled is True
        assert control.duel_enabled is True


@pytest.mark.asyncio
async def test_application_control_follows_on_chain_ownership(client, app) -> None:
    """Switching the application off tracks who owns the contract now.

    The session gate only proves the caller holds a session for the configured
    admin wallet. It says nothing about whether that wallet still owns
    anything, so after an ownership transfer the former admin could still take
    the app down. Every other control action already asks the chain; this one
    does too now.
    """

    class TransferredOwner(FakeControlTonClient):
        async def get_contract_admin_state(self, mode: str, address: str):
            state = await super().get_contract_admin_state(mode, address)
            return replace(state, owner="0:" + "99" * 32)

    app.state.ton_client = TransferredOwner()
    authorize_control(client)

    response = await client.patch(
        "/api/v1/control/application",
        json={"maintenance_enabled": True},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "connected wallet is not contract owner"


@pytest.mark.asyncio
async def test_withdrawal_carries_the_gas_the_contract_demands(client, app) -> None:
    """Both contracts require more gas for a withdrawal than for anything else.

    The panel sent the same amount for every admin call, so a withdrawal
    arrived under the contract's floor and was rejected outright — the owner
    saw a failed contract call and a bounce, with no clue why.
    """
    app.state.ton_client = FakeControlTonClient()
    authorize_control(client)

    withdrawal = await client.post(
        "/api/v1/control/transactions",
        json={"mode": "duel", "action": "withdraw_surplus", "amount_nano": 100_000_000},
    )
    assert withdrawal.status_code == 200, withdrawal.text
    # WITHDRAW_GAS_BUFFER is 50_000_000 in both contracts.
    assert int(withdrawal.json()["amount_nano"]) >= 50_000_000

    pause = await client.post(
        "/api/v1/control/transactions",
        json={"mode": "duel", "action": "pause", "paused": True},
    )
    assert pause.status_code == 200, pause.text
    assert int(pause.json()["amount_nano"]) == 30_000_000


@pytest.mark.asyncio
async def test_participants_report_what_each_person_actually_did(client, app) -> None:
    """The panel lists people, not rows.

    A participant who relinked a wallet, or who left a position behind on a
    network the application has since moved away from, must still appear once
    with figures that match this network.
    """
    from app.models import ReferralAttribution, User, Wallet
    from app.modules.bank.models import BankPosition, BankPositionStatus

    settings = get_settings()
    async with app.state.session_factory() as db:
        inviter = User(id="u-inviter", telegram_id=501, first_name="Roma", username="akxiemy")
        invitee = User(id="u-invitee", telegram_id=502, first_name="Flayni")
        db.add_all([inviter, invitee])
        db.add(
            Wallet(
                user_id=inviter.id,
                network=settings.ton_network_id,
                address="0:" + "33" * 32,
                public_key="cc" * 32,
                active=True,
            )
        )
        db.add(
            ReferralAttribution(
                inviter_user_id=inviter.id,
                invitee_user_id=invitee.id,
                code="LOOP1",
                status="qualified",
            )
        )
        for index, (status, network) in enumerate(
            (
                (BankPositionStatus.PAYOUT_SENT, settings.ton_network_id),
                (BankPositionStatus.QUEUED, settings.ton_network_id),
                (BankPositionStatus.QUEUED, settings.ton_network_id + 1),
            )
        ):
            db.add(
                BankPosition(
                    position_id=900 + index,
                    user_id=inviter.id,
                    owner_wallet="0:" + "33" * 32,
                    network=network,
                    contract_address="0:" + "12" * 32,
                    query_id=900 + index,
                    principal_nano=1_000_000_000,
                    multiplier_bps=12_500,
                    target_payout_nano=1_250_000_000,
                    remaining_amount_nano=0,
                    current_status=status.value,
                )
            )
        await db.commit()

    authorize_control(client)
    response = await client.get("/api/v1/control/participants")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2

    people = {row["telegram_id"]: row for row in body["participants"]}
    roma = people[501]
    assert roma["username"] == "akxiemy"
    assert roma["wallet"] == "0:" + "33" * 32
    assert roma["bank_positions"] == 2, "the other network's position must not count"
    assert roma["bank_active"] == 1
    assert roma["bank_deposited_nano"] == 2_000_000_000
    assert roma["bank_received_nano"] == 1_250_000_000
    assert roma["referrals_qualified"] == 1

    flayni = people[502]
    assert flayni["bank_positions"] == 0
    assert flayni["wallet"] is None
    assert flayni["referrals_qualified"] == 0


@pytest.mark.asyncio
async def test_participants_stay_behind_the_owner_session(client, app) -> None:
    app.state.ton_client = FakeControlTonClient()
    assert (await client.get("/api/v1/control/participants")).status_code == 401


@pytest.mark.asyncio
async def test_referral_payout_queue_closes_only_after_ton_proof(client, app) -> None:
    from sqlalchemy import select

    from app.models import (
        ReferralAttribution,
        ReferralPayoutRequest,
        ReferralReward,
        User,
    )

    app.state.ton_client = FakeControlTonClient()
    async with app.state.session_factory() as db:
        inviter = User(telegram_id=6001, first_name="Owner", username="owner")
        invitee = User(telegram_id=6002, first_name="Guest")
        db.add_all([inviter, invitee])
        await db.flush()
        attribution = ReferralAttribution(
            inviter_user_id=inviter.id,
            invitee_user_id=invitee.id,
            code="proof-code",
            status="qualified",
        )
        db.add(attribution)
        await db.flush()
        payout = ReferralPayoutRequest(
            user_id=inviter.id,
            address="0:" + "44" * 32,
            amount_nano=700_000_000,
        )
        db.add(payout)
        await db.flush()
        db.add_all(
            [
                ReferralReward(
                    attribution_id=attribution.id,
                    cause="fee_share:a",
                    reward_nano=300_000_000,
                    payout_request_id=payout.id,
                ),
                ReferralReward(
                    attribution_id=attribution.id,
                    cause="fee_share:b",
                    reward_nano=400_000_000,
                    payout_request_id=payout.id,
                ),
            ]
        )
        await db.commit()
        payout_id = payout.id

    authorize_control(client)
    queue = await client.get("/api/v1/control/referral-payouts")
    assert queue.status_code == 200, queue.text
    assert queue.json()["payouts"][0]["state"] == "requested"

    prepared = await client.post(
        f"/api/v1/control/referral-payouts/{payout_id}/transaction", json={}
    )
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["sender_address"] == OWNER
    assert prepared.json()["amount_nano"] == "700000000"

    confirmed = await client.post(
        f"/api/v1/control/referral-payouts/{payout_id}/confirm",
        json={"signed_boc": "A" * 32},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["state"] == "paid"
    assert confirmed.json()["payout_tx_hash"] == "AB" * 32

    async with app.state.session_factory() as db:
        rewards = (
            await db.scalars(
                select(ReferralReward).where(ReferralReward.payout_request_id == payout_id)
            )
        ).all()
        assert len(rewards) == 2
        assert {reward.payout_tx_hash for reward in rewards} == {"AB" * 32}


@pytest.mark.asyncio
async def test_control_analytics_uses_server_confirmed_events(client, app) -> None:
    from app.models import AuthExchange, User, Wallet
    from app.modules.duel.models import Duel, DuelOffer, DuelState, OfferState

    now = datetime.now(UTC)
    async with app.state.session_factory() as db:
        user = User(telegram_id=7001, first_name="Analytics", created_at=now)
        pending_user = User(telegram_id=7002, first_name="Pending", created_at=now)
        db.add_all([user, pending_user])
        await db.flush()
        db.add_all(
            [
                AuthExchange(
                    digest=b"x" * 32,
                    user_id=user.id,
                    auth_date=now,
                    expires_at=now,
                    created_at=now,
                ),
                Wallet(
                    user_id=user.id,
                    network=get_settings().ton_network_id,
                    address="0:" + "55" * 32,
                    public_key="55" * 32,
                ),
            ]
        )
        settings = get_settings()
        funded_offer = DuelOffer(
            onchain_offer_id=7001,
            query_id=7001,
            user_id=user.id,
            owner_wallet="0:" + "66" * 32,
            network=settings.ton_network_id,
            contract_address=settings.effective_duel_contract_address,
            chance_bps=5_000,
            total_pool_nano=2_000_000_000,
            stake_nano=1_000_000_000,
            opponent_stake_nano=1_000_000_000,
            fee_bps=1_000,
            payout_nano=1_800_000_000,
            commitment_hex="66" * 32,
            state=OfferState.SETTLED.value,
            funding_tx_hash="66" * 32,
            expires_at=now,
        )
        pending_offer = DuelOffer(
            onchain_offer_id=7002,
            query_id=7002,
            user_id=pending_user.id,
            owner_wallet="0:" + "77" * 32,
            network=settings.ton_network_id,
            contract_address=settings.effective_duel_contract_address,
            chance_bps=5_000,
            total_pool_nano=2_000_000_000,
            stake_nano=1_000_000_000,
            opponent_stake_nano=1_000_000_000,
            fee_bps=1_000,
            payout_nano=1_800_000_000,
            commitment_hex="77" * 32,
            state=OfferState.PENDING_FUNDING.value,
            expires_at=now,
        )
        db.add_all([funded_offer, pending_offer])
        await db.flush()
        db.add_all(
            [
                Duel(
                    onchain_duel_id=7001,
                    network=settings.ton_network_id,
                    offer_a_id=funded_offer.id,
                    offer_b_id=pending_offer.id,
                    state=DuelState.SETTLED.value,
                    reveal_deadline=now,
                    settled_at=now,
                ),
                Duel(
                    onchain_duel_id=7002,
                    network=settings.ton_network_id,
                    offer_a_id=funded_offer.id,
                    offer_b_id=pending_offer.id,
                    state=DuelState.REFUNDED.value,
                    reveal_deadline=now,
                    settled_at=now,
                ),
            ]
        )
        await db.commit()

    authorize_control(client)
    response = await client.get("/api/v1/control/analytics?days=7")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["days"] == 7
    assert body["active_users"] == 1
    assert body["funnel"]["registered"] == 2
    assert body["funnel"]["wallet_connected"] == 1
    assert body["funnel"]["duel_started"] == 1
    assert body["duel_settled"] == 1
    assert body["daily"][-1]["active_users"] == 1
    assert body["daily"][-1]["duel_settled"] == 1
