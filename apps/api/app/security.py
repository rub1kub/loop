import base64
import hashlib
import hmac
import json
import struct
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .config import Settings


class AuthenticationError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramIdentity:
    telegram_id: int
    username: str | None
    first_name: str
    last_name: str | None
    language_code: str | None
    photo_url: str | None
    auth_date: datetime
    start_param: str | None
    digest: bytes


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def validate_telegram_init_data(
    raw: str, bot_token: str, settings: Settings, now: datetime | None = None
) -> TelegramIdentity:
    if not bot_token:
        raise AuthenticationError("bot authentication is not configured")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=64)
    except (ValueError, UnicodeDecodeError) as exc:
        raise AuthenticationError("malformed Telegram initData") from exc
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)) or "hash" not in keys:
        raise AuthenticationError("duplicate or missing initData fields")
    values = dict(pairs)
    supplied_hash = values.pop("hash")
    if len(supplied_hash) != 64:
        raise AuthenticationError("invalid initData hash")
    try:
        bytes.fromhex(supplied_hash)
    except ValueError as exc:
        raise AuthenticationError("invalid initData hash") from exc
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied_hash.lower()):
        raise AuthenticationError("invalid initData signature")

    current = now or datetime.now(UTC)
    try:
        auth_date = datetime.fromtimestamp(int(values["auth_date"]), UTC)
        user = json.loads(values["user"])
        telegram_id = int(user["id"])
        first_name = str(user["first_name"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OverflowError) as exc:
        raise AuthenticationError("invalid Telegram identity") from exc
    age = (current - auth_date).total_seconds()
    if age > settings.telegram_auth_max_age_seconds:
        raise AuthenticationError("expired Telegram initData")
    if age < -settings.telegram_future_skew_seconds:
        raise AuthenticationError("Telegram initData is from the future")
    if telegram_id <= 0 or telegram_id > 2**63 - 1:
        raise AuthenticationError("invalid Telegram user id")
    return TelegramIdentity(
        telegram_id=telegram_id,
        username=_optional_string(user.get("username"), 64),
        first_name=first_name[:128],
        last_name=_optional_string(user.get("last_name"), 128),
        language_code=_optional_string(user.get("language_code"), 16),
        photo_url=_optional_string(user.get("photo_url"), 2048),
        auth_date=auth_date,
        start_param=_optional_string(values.get("start_param"), 512),
        digest=hashlib.sha256(raw.encode()).digest(),
    )


def _optional_string(value: Any, limit: int) -> str | None:
    return value[:limit] if isinstance(value, str) and value else None


def issue_session(
    user_id: str,
    telegram_id: int,
    session_id: str,
    settings: Settings,
    issued_at: datetime | None = None,
) -> tuple[str, datetime]:
    issued = (issued_at or datetime.now(UTC)).replace(microsecond=0)
    expires = issued + timedelta(seconds=settings.session_ttl_seconds)
    payload = {
        "aud": "loop-api",
        "exp": int(expires.timestamp()),
        "iat": int(issued.timestamp()),
        "sid": session_id,
        "sub": user_id,
        "tg": telegram_id,
    }
    encoded = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(
        settings.session_secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256
    ).digest()
    return f"{encoded}.{_b64url_encode(signature)}", expires


def decode_session(token: str, settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected = hmac.new(
            settings.session_secret.get_secret_value().encode(), encoded.encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(supplied_signature)):
            raise AuthenticationError("invalid session")
        payload = json.loads(_b64url_decode(encoded))
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AuthenticationError("invalid session") from exc
    current_ts = int((now or datetime.now(UTC)).timestamp())
    if payload.get("aud") != "loop-api" or not isinstance(payload.get("sub"), str):
        raise AuthenticationError("invalid session claims")
    if not isinstance(payload.get("exp"), int) or payload["exp"] <= current_ts:
        raise AuthenticationError("expired session")
    if not isinstance(payload.get("iat"), int) or payload["iat"] > current_ts + 30:
        raise AuthenticationError("invalid session time")
    return payload


def canonical_raw_address(address: str) -> str:
    try:
        workchain_text, hash_text = address.split(":", 1)
        workchain = int(workchain_text)
        address_hash = bytes.fromhex(hash_text)
    except (ValueError, TypeError) as exc:
        raise AuthenticationError("wallet address must be raw workchain:hash") from exc
    if workchain not in {-1, 0} or len(address_hash) != 32:
        raise AuthenticationError("invalid wallet address")
    return f"{workchain}:{address_hash.hex().upper()}"


def verify_ton_proof(
    *,
    address: str,
    network: int,
    public_key_hex: str,
    timestamp: int,
    domain: str,
    domain_length: int,
    signature_b64: str,
    payload: str,
    expected_payload: str,
    settings: Settings,
    now: datetime | None = None,
) -> str:
    canonical = canonical_raw_address(address)
    if network != settings.ton_network_id:
        raise AuthenticationError("wrong TON network")
    if domain != settings.public_origin.removeprefix("https://").removeprefix("http://"):
        raise AuthenticationError("wrong TON proof domain")
    domain_bytes = domain.encode()
    if domain_length != len(domain_bytes) or payload != expected_payload:
        raise AuthenticationError("invalid TON proof binding")
    current_ts = int((now or datetime.now(UTC)).timestamp())
    if abs(current_ts - timestamp) > settings.ton_proof_ttl_seconds:
        raise AuthenticationError("expired TON proof")
    workchain_text, hash_text = canonical.split(":", 1)
    message = (
        b"ton-proof-item-v2/"
        + struct.pack("<i", int(workchain_text))
        + bytes.fromhex(hash_text)
        + struct.pack("<I", len(domain_bytes))
        + domain_bytes
        + struct.pack("<Q", timestamp)
        + payload.encode()
    )
    digest = hashlib.sha256(
        b"\xff\xff" + b"ton-connect" + hashlib.sha256(message).digest()
    ).digest()
    try:
        signature = base64.b64decode(signature_b64, validate=True)
        public_key = bytes.fromhex(public_key_hex)
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, digest)
    except (ValueError, InvalidSignature) as exc:
        raise AuthenticationError("invalid TON proof signature") from exc
    return canonical
