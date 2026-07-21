import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from tonsdk.utils import Address  # type: ignore[import-untyped]

from .config import Settings


class TonProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ContractState:
    address: str
    status: str
    balance_nano: int
    code_hash: str
    last_transaction_hash: str | None
    last_transaction_lt: int | None


@dataclass(frozen=True)
class TransactionProof:
    transaction_hash: str
    account: str
    logical_time: int
    masterchain_seqno: int
    confirmed_at: datetime


@dataclass(frozen=True)
class JettonWalletState:
    owner_address: str
    jetton_master: str
    wallet_address: str | None
    balance_nano: int


class TonClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self.http = http
        self.settings = settings

    @property
    def headers(self) -> dict[str, str]:
        key = self.settings.toncenter_api_key.get_secret_value()
        return {"X-API-Key": key} if key else {}

    async def get_wallet_public_key(self, address: str) -> str:
        response = await self.http.post(
            f"{self.settings.toncenter_url}/api/v2/runGetMethod",
            headers=self.headers,
            json={"address": address, "method": "get_public_key", "stack": []},
        )
        if response.status_code != 200:
            raise TonProviderError("TON provider rejected wallet getter")
        body = response.json()
        if not body.get("ok"):
            raise TonProviderError("wallet does not expose a public key")
        try:
            value = body["result"]["stack"][0][1]
            key = int(value, 0).to_bytes(32, "big").hex()
        except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
            raise TonProviderError("malformed wallet public key response") from exc
        return key

    async def get_native_balance(self, address: str) -> int:
        response = await self.http.get(
            f"{self.settings.toncenter_url}/api/v2/getAddressBalance",
            headers=self.headers,
            params={"address": address},
        )
        if response.status_code != 200:
            raise TonProviderError("TON balance provider unavailable")
        body = response.json()
        try:
            return int(body["result"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TonProviderError("malformed TON balance response") from exc

    async def get_jetton_wallet(
        self, owner_address: str, jetton_master: str
    ) -> JettonWalletState:
        owner = normalize_address(owner_address)
        master = normalize_address(jetton_master)
        response = await self.http.get(
            f"{self.settings.toncenter_url}/api/v3/jetton/wallets",
            headers=self.headers,
            params={"owner_address": owner, "jetton_master": master, "limit": 2},
        )
        if response.status_code != 200:
            raise TonProviderError("Jetton provider unavailable")
        payload: Any = response.json()
        wallets = payload.get("jetton_wallets") if isinstance(payload, dict) else None
        if not isinstance(wallets, list):
            raise TonProviderError("malformed Jetton response")
        if not wallets:
            return JettonWalletState(owner, master, None, 0)
        if len(wallets) != 1 or not isinstance(wallets[0], dict):
            raise TonProviderError("ambiguous Jetton wallet response")
        wallet = wallets[0]
        wallet_owner = wallet.get("owner") or wallet.get("owner_address")
        wallet_master = wallet.get("jetton") or wallet.get("jetton_master")
        wallet_address = wallet.get("address")
        if (
            not isinstance(wallet_owner, str)
            or not isinstance(wallet_master, str)
            or not isinstance(wallet_address, str)
        ):
            raise TonProviderError("Jetton proof is missing owner or master")
        if normalize_address(wallet_owner) != owner or normalize_address(wallet_master) != master:
            raise TonProviderError("Jetton wallet owner or master mismatch")
        try:
            balance = int(wallet["balance"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TonProviderError("malformed Jetton balance") from exc
        return JettonWalletState(owner, master, normalize_address(wallet_address), balance)

    async def get_holder_balance(self, owner_address: str, jetton_master: str) -> int:
        return (await self.get_jetton_wallet(owner_address, jetton_master)).balance_nano

    async def get_contract_state(self, address: str) -> ContractState:
        response = await self.http.get(
            f"{self.settings.toncenter_url}/api/v3/accountStates",
            headers=self.headers,
            params={"address": address, "include_boc": "false"},
        )
        if response.status_code != 200:
            raise TonProviderError("TON contract state provider unavailable")
        payload: Any = response.json()
        accounts = payload.get("accounts") if isinstance(payload, dict) else None
        if (
            not isinstance(accounts, list)
            or len(accounts) != 1
            or not isinstance(accounts[0], dict)
        ):
            raise TonProviderError("TON contract state is missing or ambiguous")
        account = accounts[0]
        status = account.get("status")
        code_hash = account.get("code_hash")
        if status != "active":
            raise TonProviderError("TON contract is not active")
        if not isinstance(code_hash, str):
            raise TonProviderError("TON contract code hash is missing")
        try:
            balance = int(account["balance"])
            last_lt = (
                int(account["last_transaction_lt"])
                if account.get("last_transaction_lt") is not None
                else None
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise TonProviderError("malformed TON contract state") from exc
        tx_hash = account.get("last_transaction_hash")
        if tx_hash is not None and not isinstance(tx_hash, str):
            raise TonProviderError("malformed last transaction hash")
        return ContractState(
            address=normalize_address(str(account.get("address") or address)),
            status=status,
            balance_nano=balance,
            code_hash=normalize_hash(code_hash),
            last_transaction_hash=tx_hash,
            last_transaction_lt=last_lt,
        )

    async def get_contract_code_hash(self, address: str) -> str:
        return (await self.get_contract_state(address)).code_hash

    async def verify_transaction(self, transaction_hash: str, account: str) -> TransactionProof:
        normalize_hash(transaction_hash)
        expected_account = normalize_address(account)
        response = await self.http.get(
            f"{self.settings.toncenter_url}/api/v3/transactions",
            headers=self.headers,
            params={"hash": transaction_hash, "limit": 2},
        )
        if response.status_code != 200:
            raise TonProviderError("TON transaction provider unavailable")
        payload: Any = response.json()
        transactions = payload.get("transactions") if isinstance(payload, dict) else None
        if (
            not isinstance(transactions, list)
            or len(transactions) != 1
            or not isinstance(transactions[0], dict)
        ):
            raise TonProviderError("TON transaction is missing or ambiguous")
        transaction = transactions[0]
        description = transaction.get("description")
        if not isinstance(description, dict):
            raise TonProviderError("TON transaction description is missing")
        compute = description.get("compute_ph")
        action = description.get("action")
        if (
            transaction.get("emulated")
            or description.get("aborted")
            or not isinstance(compute, dict)
            or compute.get("success") is not True
            or (isinstance(action, dict) and action.get("success") is False)
        ):
            raise TonProviderError("TON transaction did not complete successfully")
        actual_account = transaction.get("account")
        if (
            not isinstance(actual_account, str)
            or normalize_address(actual_account) != expected_account
        ):
            raise TonProviderError("TON transaction account mismatch")
        mc_seqno = transaction.get("mc_block_seqno")
        if not isinstance(mc_seqno, int) or mc_seqno <= 0:
            raise TonProviderError("TON transaction has no masterchain finality proof")
        try:
            logical_time = int(transaction["lt"])
            confirmed_at = datetime.fromtimestamp(int(transaction["now"]), UTC)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise TonProviderError("malformed TON transaction proof") from exc
        return TransactionProof(
            transaction_hash=transaction_hash,
            account=expected_account,
            logical_time=logical_time,
            masterchain_seqno=mc_seqno,
            confirmed_at=confirmed_at,
        )


def normalize_address(value: str) -> str:
    try:
        return Address(value).to_string(is_user_friendly=False).lower()
    except Exception as exc:
        raise TonProviderError("malformed TON address") from exc


def normalize_hash(value: str) -> str:
    raw = value.removeprefix("0x")
    try:
        decoded = bytes.fromhex(raw)
    except ValueError:
        try:
            decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_")
        except (ValueError, TypeError) as exc:
            raise TonProviderError("malformed TON hash") from exc
    if len(decoded) != 32:
        raise TonProviderError("malformed TON hash")
    return decoded.hex().upper()


def explorer_transaction_url(network: int, transaction_hash: str) -> str:
    host = "testnet.tonviewer.com" if network == -3 else "tonviewer.com"
    return f"https://{host}/transaction/{quote(transaction_hash, safe='')}"


def commitment_context_hash(offer_id: int, address: str) -> str:
    return hashlib.sha256(f"LOOP_DUEL_V1:{offer_id}:{address}".encode()).hexdigest()
