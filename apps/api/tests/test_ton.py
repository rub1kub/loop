import base64

import httpx
import pytest
from tonsdk.boc import Cell  # type: ignore[import-untyped]
from tonsdk.utils import Address  # type: ignore[import-untyped]

from app.config import get_settings
from app.ton import (
    TonClient,
    TonProviderError,
    duel_invite_public_key,
    sign_direct_accept_permit,
    verify_direct_accept_permit,
)


def hash_b64(byte: int) -> str:
    return base64.b64encode(bytes([byte]) * 32).decode()


def message_body(*values: tuple[int, int]) -> dict[str, dict[str, str]]:
    cell = Cell()
    for value, bits in values:
        cell.bits.write_uint(value, bits)
    return {"message_content": {"body": base64.b64encode(cell.to_boc(False)).decode()}}


def address_stack(address: str) -> list[object]:
    cell = Cell()
    cell.bits.write_address(Address(address))
    return ["cell", {"bytes": base64.b64encode(cell.to_boc(False)).decode()}]


def test_direct_permit_is_bound_to_network_contract_offer_and_invited_wallet() -> None:
    private_key = get_settings().duel_invite_signing_key.get_secret_value()
    public_key = duel_invite_public_key(private_key)
    context = {
        "network": -3,
        "contract_address": "0:" + "11" * 32,
        "invite_id_hex": "22" * 32,
        "counter_offer_id": 77,
        "invited_address": "0:" + "33" * 32,
        "valid_until": 2_000_000_000,
    }
    signature = sign_direct_accept_permit(private_key, **context)
    assert verify_direct_accept_permit(public_key, signature, **context)
    assert not verify_direct_accept_permit(
        public_key,
        signature,
        **{**context, "invited_address": "0:" + "44" * 32},
    )
    assert not verify_direct_accept_permit(public_key, signature, **{**context, "network": -239})


@pytest.mark.asyncio
async def test_contract_transaction_and_jetton_proofs_are_fail_closed() -> None:
    account = "0:" + "11" * 32
    owner = "0:" + "22" * 32
    master = "0:" + "33" * 32
    jetton_wallet = "0:" + "44" * 32
    tx_hash = hash_b64(5)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/accountStates"):
            return httpx.Response(
                200,
                json={
                    "accounts": [
                        {
                            "address": account,
                            "status": "active",
                            "balance": "123",
                            "code_hash": hash_b64(6),
                            "last_transaction_hash": tx_hash,
                            "last_transaction_lt": "77",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/transactions"):
            return httpx.Response(
                200,
                json={
                    "transactions": [
                        {
                            "account": account,
                            "hash": tx_hash,
                            "lt": "77",
                            "now": 1_800_000_000,
                            "mc_block_seqno": 55,
                            "emulated": False,
                            "description": {
                                "aborted": False,
                                "compute_ph": {"success": True},
                                "action": {"success": True},
                            },
                        }
                    ]
                },
            )
        if request.url.path.endswith("/jetton/wallets"):
            return httpx.Response(
                200,
                json={
                    "jetton_wallets": [
                        {
                            "address": jetton_wallet,
                            "owner": owner,
                            "jetton": master,
                            "balance": "999",
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TonClient(http, get_settings())
        contract = await client.get_contract_state(account)
        assert contract.status == "active"
        assert contract.balance_nano == 123
        proof = await client.verify_transaction(tx_hash, account)
        assert proof.masterchain_seqno == 55
        jetton = await client.get_jetton_wallet(owner, master)
        assert jetton.wallet_address == jetton_wallet
        assert jetton.balance_nano == 999

        with pytest.raises(TonProviderError, match="account mismatch"):
            await client.verify_transaction(tx_hash, "0:" + "aa" * 32)


@pytest.mark.asyncio
async def test_contract_admin_state_parses_extended_and_legacy_getters() -> None:
    owner = "0:" + "22" * 32
    treasury = "0:" + "33" * 32

    def extended_handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/runGetMethod")
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "exit_code": 0,
                    "stack": [
                        address_stack(owner),
                        address_stack(treasury),
                        ["num", "0xfa"],
                        ["num", "-0x1"],
                        ["num", "0x3b9aca00"],
                    ],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(extended_handler)) as http:
        state = await TonClient(http, get_settings()).get_contract_admin_state(
            "duel", "0:" + "11" * 32
        )
        assert state.owner == owner
        assert state.treasury == treasury
        assert state.fee_bps == 250
        assert state.paused is True
        assert state.locked_nano == 1_000_000_000
        assert state.extended_controls is True

    calls = 0

    def legacy_handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"ok": False, "result": {"exit_code": 11}})
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "exit_code": 0,
                    "stack": [
                        address_stack(owner),
                        address_stack(treasury),
                        ["num", "0x64"],
                        ["num", "0x0"],
                        ["num", "0x0"],
                        ["num", "0x1"],
                        ["num", "0x75bcd15"],
                    ],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(legacy_handler)) as http:
        state = await TonClient(http, get_settings()).get_contract_admin_state(
            "bank", "0:" + "12" * 32
        )
        assert state.fee_bps == 100
        assert state.locked_nano == 123_456_789
        assert state.extended_controls is False


@pytest.mark.asyncio
async def test_transaction_without_masterchain_inclusion_is_rejected() -> None:
    tx_hash = hash_b64(7)
    account = "0:" + "55" * 32

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "transactions": [
                    {
                        "account": account,
                        "hash": tx_hash,
                        "lt": "1",
                        "now": 1_800_000_000,
                        "emulated": False,
                        "description": {
                            "aborted": False,
                            "compute_ph": {"success": True},
                            "action": {"success": True},
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TonProviderError, match="masterchain finality"):
            await TonClient(http, get_settings()).verify_transaction(tx_hash, account)


@pytest.mark.asyncio
async def test_duel_canary_requires_matching_reveal_and_payout_proof() -> None:
    tx_hash = hash_b64(8)
    account = "0:" + "66" * 32
    duel_id = 8_500_000_000_000_001

    transaction = {
        "account": account,
        "hash": tx_hash,
        "lt": "88",
        "now": 1_800_000_000,
        "mc_block_seqno": 56,
        "emulated": False,
        "description": {
            "aborted": False,
            "compute_ph": {"success": True},
            "action": {"success": True},
        },
        "in_msg": message_body(
            (0x4C4F4F04, 32),
            (duel_id, 64),
            (duel_id, 64),
            (duel_id, 64),
            (1, 256),
        ),
        "out_msgs": [
            message_body(
                (0x4C4F4F11, 32),
                (duel_id, 64),
                (duel_id, 64),
                (duel_id, 64),
                (1, 8),
            )
        ],
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"transactions": [transaction]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TonClient(http, get_settings())
        proof = await client.verify_duel_settlement(tx_hash, account, duel_id)
        assert proof.masterchain_seqno == 56
        with pytest.raises(TonProviderError, match="requested DUEL settlement"):
            await client.verify_duel_settlement(tx_hash, account, duel_id + 1)
