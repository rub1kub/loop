import base64
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from tonsdk.boc import Cell  # type: ignore[import-untyped]
from tonsdk.utils import Address  # type: ignore[import-untyped]

from .config import Settings


class TonProviderError(RuntimeError):
    pass


DUEL_DIRECT_ACCEPT_DOMAIN = 0x4C4F4F62
DUEL_REVEAL = 0x4C4F4F04
DUEL_PAYOUT = 0x4C4F4F11


@dataclass(frozen=True)
class ContractState:
    address: str
    status: str
    balance_nano: int
    code_hash: str
    last_transaction_hash: str | None
    last_transaction_lt: int | None


@dataclass(frozen=True)
class ContractAdminState:
    owner: str
    treasury: str
    fee_bps: int
    paused: bool
    locked_nano: int
    extended_controls: bool


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
    def __init__(
        self,
        http: httpx.AsyncClient,
        settings: Settings,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.http = http
        self.settings = settings
        self.base_url = (base_url or settings.toncenter_url).rstrip("/")
        self.api_key = (
            api_key if api_key is not None else settings.toncenter_api_key.get_secret_value()
        )

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key} if self.api_key else {}

    async def get_wallet_public_key(self, address: str) -> str:
        response = await self.http.post(
            f"{self.base_url}/api/v2/runGetMethod",
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
            f"{self.base_url}/api/v2/getAddressBalance",
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

    async def get_jetton_wallet(self, owner_address: str, jetton_master: str) -> JettonWalletState:
        owner = normalize_address(owner_address)
        master = normalize_address(jetton_master)
        response = await self.http.get(
            f"{self.base_url}/api/v3/jetton/wallets",
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
            f"{self.base_url}/api/v3/accountStates",
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

    async def _run_get_method(self, address: str, method: str) -> list[Any]:
        response = await self.http.post(
            f"{self.base_url}/api/v2/runGetMethod",
            headers=self.headers,
            json={"address": address, "method": method, "stack": []},
        )
        if response.status_code != 200:
            raise TonProviderError("TON provider rejected contract getter")
        body: Any = response.json()
        result = body.get("result") if isinstance(body, dict) else None
        stack = result.get("stack") if isinstance(result, dict) else None
        exit_code = result.get("exit_code") if isinstance(result, dict) else None
        if (
            not isinstance(body, dict)
            or body.get("ok") is not True
            or exit_code not in {None, 0, 1}
            or not isinstance(stack, list)
        ):
            raise TonProviderError(f"contract getter {method} is unavailable")
        return stack

    async def get_contract_admin_state(
        self,
        mode: str,
        address: str,
    ) -> ContractAdminState:
        if mode not in {"bank", "duel"}:
            raise TonProviderError("unknown contract mode")
        extended = True
        try:
            stack = await self._run_get_method(address, "adminState")
            owner_index, treasury_index, fee_index, paused_index, locked_index = range(5)
        except TonProviderError:
            extended = False
            stack = await self._run_get_method(address, "contractConfig")
            owner_index, treasury_index, fee_index = 0, 1, 2
            paused_index, locked_index = ((3, 6) if mode == "bank" else (6, 7))
        try:
            owner = _stack_address(stack[owner_index])
            treasury = _stack_address(stack[treasury_index])
            fee_bps = _stack_number(stack[fee_index])
            paused = _stack_number(stack[paused_index]) != 0
            locked_nano = _stack_number(stack[locked_index])
        except (IndexError, TypeError, ValueError) as exc:
            raise TonProviderError("malformed contract admin state") from exc
        if not 0 <= fee_bps <= 10_000 or locked_nano < 0:
            raise TonProviderError("contract admin state is outside valid bounds")
        return ContractAdminState(
            owner=owner,
            treasury=treasury,
            fee_bps=fee_bps,
            paused=paused,
            locked_nano=locked_nano,
            extended_controls=extended,
        )

    async def _verified_transaction(
        self, transaction_hash: str, account: str
    ) -> tuple[TransactionProof, dict[str, Any]]:
        normalize_hash(transaction_hash)
        expected_account = normalize_address(account)
        response = await self.http.get(
            f"{self.base_url}/api/v3/transactions",
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
        return (
            TransactionProof(
                transaction_hash=transaction_hash,
                account=expected_account,
                logical_time=logical_time,
                masterchain_seqno=mc_seqno,
                confirmed_at=confirmed_at,
            ),
            transaction,
        )

    async def verify_transaction(self, transaction_hash: str, account: str) -> TransactionProof:
        proof, _ = await self._verified_transaction(transaction_hash, account)
        return proof

    async def verify_duel_settlement(
        self,
        transaction_hash: str,
        account: str,
        duel_id: int,
    ) -> TransactionProof:
        if not 0 < duel_id < 2**64:
            raise TonProviderError("invalid DUEL canary duel id")
        proof, transaction = await self._verified_transaction(transaction_hash, account)
        incoming = transaction.get("in_msg")
        if not isinstance(incoming, dict):
            raise TonProviderError("DUEL settlement input message is missing")
        parser = message_body_parser(incoming)
        try:
            opcode = parser.read_uint(32)
            parser.read_uint(64)
            incoming_duel_id = parser.read_uint(64)
        except Exception as exc:
            raise TonProviderError("malformed DUEL settlement input message") from exc
        if opcode != DUEL_REVEAL or incoming_duel_id != duel_id:
            raise TonProviderError("transaction is not the requested DUEL settlement reveal")

        matching_payouts = 0
        outgoing = transaction.get("out_msgs")
        if not isinstance(outgoing, list):
            raise TonProviderError("DUEL settlement output messages are missing")
        for message in outgoing:
            if not isinstance(message, dict):
                continue
            payout_duel_id: int | None = None
            try:
                payout = message_body_parser(message)
                if payout.read_uint(32) == DUEL_PAYOUT:
                    payout.read_uint(64)
                    payout_duel_id = payout.read_uint(64)
            except Exception:
                payout_duel_id = None
            if payout_duel_id == duel_id:
                matching_payouts += 1
        if matching_payouts != 1:
            raise TonProviderError("DUEL settlement payout proof is missing or ambiguous")
        return proof


def normalize_address(value: str) -> str:
    try:
        return str(Address(value).to_string(is_user_friendly=False)).lower()
    except Exception as exc:
        raise TonProviderError("malformed TON address") from exc


def _stack_number(item: Any) -> int:
    if (
        not isinstance(item, list)
        or len(item) != 2
        or item[0] != "num"
        or not isinstance(item[1], str)
    ):
        raise TonProviderError("TON getter number is malformed")
    return int(item[1], 0)


def _stack_address(item: Any) -> str:
    if not isinstance(item, list) or len(item) != 2 or item[0] not in {"cell", "slice"}:
        raise TonProviderError("TON getter address is malformed")
    payload = item[1]
    encoded: str | None = None
    if isinstance(payload, str):
        encoded = payload
    elif isinstance(payload, dict):
        encoded = payload.get("bytes")
        if not isinstance(encoded, str):
            data = payload.get("object", {}).get("data", {})
            encoded = data.get("b64") if isinstance(data, dict) else None
    if not encoded:
        raise TonProviderError("TON getter address cell is missing")
    try:
        cells = Cell.one_from_boc(base64.b64decode(encoded))
        cell = cells[0] if isinstance(cells, list) else cells
        address = cell.begin_parse().read_msg_addr()
        if address is None:
            raise ValueError
        return normalize_address(address.to_string(is_user_friendly=False))
    except Exception as exc:
        raise TonProviderError("TON getter address cell is malformed") from exc


def message_body_parser(message: dict[str, Any]) -> Any:
    content = message.get("message_content")
    body = content.get("body") if isinstance(content, dict) else None
    if not isinstance(body, str) or not body:
        raise TonProviderError("TON message body is missing")
    try:
        cells = Cell.one_from_boc(base64.b64decode(body))
        cell = cells[0] if isinstance(cells, list) else cells
        return cell.begin_parse()
    except Exception as exc:
        raise TonProviderError("malformed TON message body") from exc


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


def duel_invite_public_key(private_seed_hex: str) -> str:
    try:
        seed = bytes.fromhex(private_seed_hex)
        if len(seed) != 32:
            raise ValueError
        public_key = Ed25519PrivateKey.from_private_bytes(seed).public_key()
    except ValueError as exc:
        raise TonProviderError("DUEL invite signing key must be 32-byte hex") from exc
    return public_key.public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def direct_accept_permit_hash(
    *,
    network: int,
    contract_address: str,
    invite_id_hex: str,
    counter_offer_id: int,
    invited_address: str,
    valid_until: int,
) -> bytes:
    try:
        invite_id = int(invite_id_hex, 16)
        if len(bytes.fromhex(invite_id_hex)) != 32:
            raise ValueError
        if not -(2**31) <= network < 2**31:
            raise ValueError
        if not 0 < counter_offer_id < 2**64 or not 0 < valid_until < 2**32:
            raise ValueError
        cell = Cell()
        cell.bits.write_uint(DUEL_DIRECT_ACCEPT_DOMAIN, 32)
        cell.bits.write_int(network, 32)
        cell.bits.write_address(Address(contract_address))
        cell.bits.write_uint(invite_id, 256)
        cell.bits.write_uint(counter_offer_id, 64)
        cell.bits.write_address(Address(invited_address))
        cell.bits.write_uint(valid_until, 32)
        return bytes(cell.bytes_hash())
    except (ValueError, OverflowError, TypeError) as exc:
        raise TonProviderError("invalid DUEL direct permit context") from exc


def sign_direct_accept_permit(
    private_seed_hex: str,
    *,
    network: int,
    contract_address: str,
    invite_id_hex: str,
    counter_offer_id: int,
    invited_address: str,
    valid_until: int,
) -> str:
    try:
        seed = bytes.fromhex(private_seed_hex)
        if len(seed) != 32:
            raise ValueError
        signature = Ed25519PrivateKey.from_private_bytes(seed).sign(
            direct_accept_permit_hash(
                network=network,
                contract_address=contract_address,
                invite_id_hex=invite_id_hex,
                counter_offer_id=counter_offer_id,
                invited_address=invited_address,
                valid_until=valid_until,
            )
        )
    except ValueError as exc:
        raise TonProviderError("DUEL invite signing key must be 32-byte hex") from exc
    return signature.hex()


def verify_direct_accept_permit(
    public_key_hex: str,
    signature_hex: str,
    **context: Any,
) -> bool:
    try:
        public_key = bytes.fromhex(public_key_hex)
        signature = bytes.fromhex(signature_hex)
        if len(public_key) != 32 or len(signature) != 64:
            return False
        Ed25519PublicKey.from_public_bytes(public_key).verify(
            signature,
            direct_accept_permit_hash(**context),
        )
    except (ValueError, InvalidSignature, TonProviderError):
        return False
    return True


def commitment_context_hash(offer_id: int, address: str) -> str:
    return hashlib.sha256(f"LOOP_DUEL_V1:{offer_id}:{address}".encode()).hexdigest()
