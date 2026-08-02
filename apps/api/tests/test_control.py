import base64
from dataclasses import replace

import pytest
from fastapi import HTTPException
from tonsdk.boc import Cell  # type: ignore[import-untyped]

from app import control_routes
from app.config import get_settings
from app.control_state import application_control, ensure_mode_enabled
from app.security import issue_control_session
from app.ton import ContractAdminState, ContractState

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

    async def get_contract_admin_state(
        self, mode: str, address: str
    ) -> ContractAdminState:
        del address
        return ContractAdminState(
            owner=OWNER,
            treasury=OWNER,
            fee_bps=100 if mode == "bank" else 250,
            paused=mode == "duel",
            locked_nano=1_000_000_000,
            extended_controls=True,
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
