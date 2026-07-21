import base64

import httpx
import pytest

from app.config import get_settings
from app.ton import TonClient, TonProviderError


def hash_b64(byte: int) -> str:
    return base64.b64encode(bytes([byte]) * 32).decode()


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
