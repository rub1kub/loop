import base64

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
