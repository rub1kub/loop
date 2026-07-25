from typing import Any

import pytest
from pydantic import ValidationError

from app.config import MAINNET_NETWORK_ID, TESTNET_NETWORK_ID, Settings


def production_settings(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "app_env": "production",
        "bot_token": "123456:test-token",
        "bot_username": "loop_test_bot",
        "telegram_webhook_secret": "w" * 32,
        "session_secret": "s" * 32,
        "metrics_token": "m" * 32,
        "control_admin_wallet": "0:" + "22" * 32,
        "public_origin": "https://loop.example",
        "cors_origins": "https://loop.example",
        "bank_contract_address": "0:" + "12" * 32,
        "bank_contract_code_hash": "AA" * 32,
        "duel_contract_address": "0:" + "11" * 32,
        "duel_contract_code_hash": "BB" * 32,
        "duel_invite_signing_key": (
            "0102030405060708090a0b0c0d0e0f00112233445566778899aabbccddeeff00"
        ),
        "duel_invite_public_key": (
            "42a8ada72bbd29ec106cc16aaca1b6d6d572962f7b8de922c295b30b5594bffd"
        ),
        "ton_network_id": TESTNET_NETWORK_ID,
        "toncenter_url": "https://testnet.toncenter.com",
    }
    values.update(overrides)
    return values


def test_production_testnet_remains_enabled_without_mainnet_gate() -> None:
    settings = Settings(_env_file=None, **production_settings())
    assert settings.ton_transactions_enabled
    assert not settings.mainnet_enabled


def test_mainnet_is_fail_closed_without_release_evidence() -> None:
    with pytest.raises(ValidationError, match="LOOP_MAINNET_ENABLED"):
        Settings(
            _env_file=None,
            **production_settings(
                ton_network_id=MAINNET_NETWORK_ID,
                toncenter_url="https://toncenter.com",
            ),
        )


def test_mainnet_requires_the_audited_release_and_canary() -> None:
    commit = "a" * 40
    with pytest.raises(ValidationError, match="two-wallet DUEL canary"):
        Settings(
            _env_file=None,
            **production_settings(
                ton_network_id=MAINNET_NETWORK_ID,
                toncenter_url="https://toncenter.com",
                mainnet_enabled=True,
                mainnet_release_commit=commit,
                mainnet_audited_commit=commit,
                mainnet_audit_report_sha256="b" * 64,
            ),
        )


def test_mainnet_accepts_only_the_exact_audited_commit() -> None:
    commit = "a" * 40
    settings = Settings(
        _env_file=None,
        **production_settings(
            ton_network_id=MAINNET_NETWORK_ID,
            toncenter_url="https://toncenter.com",
            mainnet_enabled=True,
            mainnet_release_commit=commit,
            mainnet_audited_commit=commit,
            mainnet_audit_report_sha256="b" * 64,
            require_duel_canary=True,
        ),
    )
    assert settings.ton_transactions_enabled

    with pytest.raises(ValidationError, match="externally audited commit"):
        Settings(
            _env_file=None,
            **production_settings(
                ton_network_id=MAINNET_NETWORK_ID,
                toncenter_url="https://toncenter.com",
                mainnet_enabled=True,
                mainnet_release_commit=commit,
                mainnet_audited_commit="c" * 40,
                mainnet_audit_report_sha256="b" * 64,
                require_duel_canary=True,
            ),
        )
