import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import urlencode

import pytest
from sqlalchemy import select

from app.models import User, Wallet


def signed_init_data() -> str:
    values = {
        "auth_date": str(int(datetime.now(UTC).timestamp())),
        "query_id": "AAE-api",
        "user": json.dumps({"id": 777000111, "first_name": "Loop"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", b"123456:test-token", hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


@pytest.mark.asyncio
async def test_auth_me_and_bank(client) -> None:
    auth = await client.post("/api/v1/auth/telegram", json={"init_data": signed_init_data()})
    assert auth.status_code == 200, auth.text
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["telegram_id"] == 777000111
    bank = await client.put("/api/v1/bank", headers=headers, json={"target_nano": 10_000_000_000})
    assert bank.status_code == 200
    assert bank.json()["target_nano"] == 10_000_000_000


@pytest.mark.asyncio
async def test_quote_requires_verified_wallet(client, app) -> None:
    auth = await client.post("/api/v1/auth/telegram", json={"init_data": signed_init_data()})
    token = auth.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    denied = await client.post(
        "/api/v1/duels/quote",
        headers=headers,
        json={
            "offer_id": 12345,
            "chance_bps": 2500,
            "total_pool_nano": 4_000_000_000,
            "commitment_hex": "ab" * 32,
        },
    )
    assert denied.status_code == 409
    async with app.state.session_factory() as db:
        user = await db.scalar(select(User).where(User.telegram_id == 777000111))
        db.add(
            Wallet(
                user_id=user.id,
                network=-3,
                address="0:" + "22" * 32,
                public_key="33" * 32,
            )
        )
        await db.commit()
    quote = await client.post(
        "/api/v1/duels/quote",
        headers=headers,
        json={
            "offer_id": 12345,
            "chance_bps": 2500,
            "total_pool_nano": 4_000_000_000,
            "commitment_hex": "ab" * 32,
        },
    )
    assert quote.status_code == 200, quote.text
    result = quote.json()
    assert result["offer"]["stake_nano"] == 1_000_000_000
    assert result["transaction"]["amount_nano"] == "1050000000"
