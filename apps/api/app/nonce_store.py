import hashlib
import json
from typing import Protocol

from redis.asyncio import Redis


class ChallengeStore(Protocol):
    async def put(self, payload: str, value: dict[str, object], ttl: int) -> None: ...

    async def consume(self, payload: str) -> dict[str, object] | None: ...


def _key(payload: str) -> str:
    return f"loop:wallet-proof:{hashlib.sha256(payload.encode()).hexdigest()}"


class RedisChallengeStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def put(self, payload: str, value: dict[str, object], ttl: int) -> None:
        await self.redis.set(
            _key(payload), json.dumps(value, separators=(",", ":")), ex=ttl, nx=True
        )

    async def consume(self, payload: str) -> dict[str, object] | None:
        script = (
            "local v=redis.call('GET',KEYS[1]); if v then redis.call('DEL',KEYS[1]); end; return v"
        )
        raw = await self.redis.eval(script, 1, _key(payload))
        return json.loads(raw) if raw else None


class MemoryChallengeStore:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, object]] = {}

    async def put(self, payload: str, value: dict[str, object], ttl: int) -> None:
        self.values[_key(payload)] = value

    async def consume(self, payload: str) -> dict[str, object] | None:
        return self.values.pop(_key(payload), None)
