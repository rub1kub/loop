import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.config import get_settings
from app.security import (
    AuthenticationError,
    decode_control_session,
    decode_session,
    issue_control_session,
    issue_session,
    validate_telegram_init_data,
)


def signed_init_data(bot_token: str, now: datetime, **overrides: str) -> str:
    values = {
        "auth_date": str(int(now.timestamp())),
        "query_id": "AAE-test",
        "user": json.dumps(
            {"id": 922337203685477000, "first_name": "Loop", "username": "loop_user"},
            separators=(",", ":"),
        ),
    }
    values.update(overrides)
    check = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_validates_telegram_init_data() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    raw = signed_init_data("123456:test-token", now, start_param="ref_SAFE")
    identity = validate_telegram_init_data(raw, "123456:test-token", get_settings(), now)
    assert identity.telegram_id == 922337203685477000
    assert identity.start_param == "ref_SAFE"


def test_rejects_tampering_duplicates_and_expiry() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    settings = get_settings()
    raw = signed_init_data("123456:test-token", now)
    with pytest.raises(AuthenticationError):
        validate_telegram_init_data(raw.replace("Loop", "Loot"), "123456:test-token", settings, now)
    with pytest.raises(AuthenticationError):
        validate_telegram_init_data(raw + "&auth_date=1", "123456:test-token", settings, now)
    desktop_launch = signed_init_data("123456:test-token", now - timedelta(minutes=30))
    validate_telegram_init_data(desktop_launch, "123456:test-token", settings, now)
    expired = signed_init_data(
        "123456:test-token",
        now - timedelta(seconds=settings.telegram_auth_max_age_seconds + 1),
    )
    with pytest.raises(AuthenticationError):
        validate_telegram_init_data(expired, "123456:test-token", settings, now)


@given(st.text(min_size=0, max_size=300))
def test_malformed_init_data_never_leaks_parser_errors(raw: str) -> None:
    with pytest.raises(AuthenticationError):
        validate_telegram_init_data(raw, "123456:test-token", get_settings())


def test_session_is_signed_and_expires() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    token, expires = issue_session("user-id", 42, "session-id", get_settings(), now)
    assert decode_session(token, get_settings(), now)["sub"] == "user-id"
    with pytest.raises(AuthenticationError):
        decode_session(token + "x", get_settings(), now)
    with pytest.raises(AuthenticationError):
        decode_session(token, get_settings(), expires + timedelta(seconds=1))


def test_control_session_has_separate_audience_and_expiry() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    address = "0:" + "22" * 32
    token, expires = issue_control_session(address, get_settings(), now)
    assert decode_control_session(token, get_settings(), now)["sub"] == address.upper()
    with pytest.raises(AuthenticationError):
        decode_session(token, get_settings(), now)
    with pytest.raises(AuthenticationError):
        decode_control_session(token, get_settings(), expires + timedelta(seconds=1))


@pytest.mark.asyncio
async def test_closed_beta_gates_the_product_but_not_the_door(client, monkeypatch) -> None:
    """Anyone signs in; the whitelist decides who gets past the waiting screen.

    Rejecting the sign-in itself would leave the warm-up week recording no
    referrals at all — attribution happens at first authentication.
    """
    from app.config import get_settings

    def init_data_for(telegram_id: int) -> str:
        return signed_init_data(
            "123456:test-token",
            datetime.now(UTC),
            user=json.dumps({"id": telegram_id, "first_name": "Loop"}, separators=(",", ":")),
        )

    def headers_for(response) -> dict[str, str]:
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    monkeypatch.setenv("LOOP_CLOSED_BETA_TELEGRAM_IDS", "1084693264")
    monkeypatch.setenv("LOOP_LAUNCH_AT", "2100-01-01T00:00:00Z")
    get_settings.cache_clear()

    waiting = await client.post(
        "/api/v1/auth/telegram", json={"init_data": init_data_for(555_001)}
    )
    assert waiting.status_code == 200, waiting.text
    me = await client.get("/api/v1/me", headers=headers_for(waiting))
    assert me.json()["app_open"] is False
    assert me.json()["launch_at"] == "2100-01-01T00:00:00Z"

    blocked = await client.get("/api/v1/bank/limits", headers=headers_for(waiting))
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "prelaunch"
    # The waiting screen's own data stays reachable.
    assert (await client.get("/api/v1/prelaunch", headers=headers_for(waiting))).status_code == 200
    assert (await client.get("/api/v1/referrals", headers=headers_for(waiting))).status_code == 200

    allowed = await client.post(
        "/api/v1/auth/telegram", json={"init_data": init_data_for(1_084_693_264)}
    )
    assert (await client.get("/api/v1/me", headers=headers_for(allowed))).json()["app_open"] is True

    # The launch happens by clock, with no deploy at the stroke of the hour.
    monkeypatch.setenv("LOOP_LAUNCH_AT", "2020-01-01T00:00:00Z")
    get_settings.cache_clear()
    assert (await client.get("/api/v1/me", headers=headers_for(waiting))).json()["app_open"] is True
    limits = await client.get("/api/v1/bank/limits", headers=headers_for(waiting))
    assert limits.status_code == 200

    monkeypatch.delenv("LOOP_CLOSED_BETA_TELEGRAM_IDS", raising=False)
    monkeypatch.delenv("LOOP_LAUNCH_AT", raising=False)
    get_settings.cache_clear()