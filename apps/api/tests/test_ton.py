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
async def test_duel_contract_domain_binds_network_address_and_signer() -> None:
    contract = "0:" + "11" * 32
    signer = int("42" * 32, 16)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {
                    "exit_code": 0,
                    "stack": [
                        address_stack("0:" + "22" * 32),
                        address_stack("0:" + "33" * 32),
                        ["num", "250"],
                        ["num", "-239"],
                        ["num", hex(signer)],
                        address_stack(contract),
                        ["num", "1"],
                        ["num", "500000000"],
                    ],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        domain = await TonClient(http, get_settings()).get_duel_contract_domain(contract)
    assert domain.network_id == -239
    assert domain.contract_address == contract
    assert domain.invite_signer_public_key == "42" * 32
    assert domain.paused is True
    assert domain.locked_nano == 500_000_000


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


@pytest.mark.asyncio
async def test_verified_jetton_balance_requires_the_master_to_derive_the_wallet() -> None:
    owner = "0:" + "aa" * 32
    master = "0:" + "bb" * 32
    real_wallet = "0:" + "cc" * 32
    counterfeit = "0:" + "dd" * 32

    def handler_for(derived: str):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/jetton/wallets"):
                return httpx.Response(
                    200,
                    json={
                        "jetton_wallets": [
                            {
                                "address": counterfeit,
                                "owner": owner,
                                "jetton": master,
                                "balance": "5000",
                            }
                        ]
                    },
                )
            # The master is the only authority on which wallet belongs to an owner.
            return httpx.Response(
                200,
                json={"ok": True, "result": {"exit_code": 0, "stack": [address_stack(derived)]}},
            )

        return handler

    settings = get_settings()
    # A contract that merely claims the right master is not proof of holding:
    # the indexed wallet must be the one the master derives.
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_for(real_wallet))) as http:
        client = TonClient(http, settings)
        with pytest.raises(TonProviderError, match="not derived"):
            await client.verified_jetton_balance(owner, master)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler_for(counterfeit))) as http:
        client = TonClient(http, settings)
        assert await client.verified_jetton_balance(owner, master) == 5000


@pytest.mark.asyncio
async def test_jetton_lookup_uses_the_filter_the_provider_honours() -> None:
    owner = "0:" + "22" * 32
    master = "0:" + "33" * 32
    other_master = "0:" + "55" * 32
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        # A filter TonCenter does not recognise is ignored rather than
        # rejected, and the reply is every jetton the owner holds. That is what
        # `jetton_master` did: the holder check then read the answer as
        # ambiguous and failed for anyone holding a second token.
        wallets = [
            {
                "address": "0:" + "44" * 32,
                "owner": owner,
                "jetton": master,
                "balance": "999",
            }
        ]
        if "jetton_address" not in request.url.params:
            wallets.append(
                {
                    "address": "0:" + "66" * 32,
                    "owner": owner,
                    "jetton": other_master,
                    "balance": "7",
                }
            )
        return httpx.Response(200, json={"jetton_wallets": wallets})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        state = await TonClient(http, get_settings()).get_jetton_wallet(owner, master)

    assert seen.get("jetton_address") == master
    assert state.balance_nano == 999
