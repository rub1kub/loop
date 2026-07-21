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
    decode_session,
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
