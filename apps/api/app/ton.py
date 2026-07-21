import hashlib

import httpx

from .config import Settings


class TonProviderError(RuntimeError):
    pass


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

    async def get_holder_balance(self, owner_address: str, jetton_master: str) -> int:
        response = await self.http.get(
            f"{self.settings.toncenter_url}/api/v3/jetton/wallets",
            headers=self.headers,
            params={"owner_address": owner_address, "jetton_master": jetton_master, "limit": 2},
        )
        if response.status_code != 200:
            raise TonProviderError("Jetton provider unavailable")
        wallets = response.json().get("jetton_wallets", [])
        if not wallets:
            return 0
        return int(wallets[0]["balance"])


def commitment_context_hash(offer_id: int, address: str) -> str:
    return hashlib.sha256(f"LOOP_DUEL_V1:{offer_id}:{address}".encode()).hexdigest()
