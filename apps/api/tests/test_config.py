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


def test_bank_debug_progress_is_scoped_by_telegram_id() -> None:
    settings = Settings(
        _env_file=None,
        bank_debug_telegram_ids="123, 456",
        bank_debug_progress_bps=6_200,
    )
    assert settings.bank_debug_progress_for(123) == 6_200
    assert settings.bank_debug_progress_for(456) == 6_200
    assert settings.bank_debug_progress_for(789) is None


def test_production_cors_is_pinned_to_the_public_origin() -> None:
    with pytest.raises(ValidationError, match="CORS"):
        Settings(
            _env_file=None,
            **production_settings(
                cors_origins="https://loop.example,https://attacker.example"
            ),
        )


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
            bank_max_principal_nano=5_000_000_000,
            max_pool_nano=2_000_000_000,
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


def test_mainnet_rejects_launch_limits_above_ten_gram() -> None:
    commit = "a" * 40
    evidence = {
        "ton_network_id": MAINNET_NETWORK_ID,
        "toncenter_url": "https://toncenter.com",
        "mainnet_enabled": True,
        "mainnet_release_commit": commit,
        "mainnet_audited_commit": commit,
        "mainnet_audit_report_sha256": "b" * 64,
        "require_duel_canary": True,
    }
    with pytest.raises(ValidationError, match="BANK launch limit"):
        Settings(
            _env_file=None,
            **production_settings(
                **evidence,
                bank_max_principal_nano=10_000_000_001,
            ),
        )
    with pytest.raises(ValidationError, match="DUEL launch limit"):
        Settings(
            _env_file=None,
            **production_settings(
                **evidence,
                bank_max_principal_nano=5_000_000_000,
                max_pool_nano=10_000_000_001,
            ),
        )


def test_an_announcement_about_tonight_stops_appearing_in_the_morning() -> None:
    # A note about the first night is worth less than nothing by tomorrow
    # afternoon, and taking it down by hand means remembering to at six in the
    # morning. The hour is part of the announcement, not a chore beside it.
    from datetime import UTC, datetime

    from app.config import Settings

    settings = Settings(
        announcement_text="LOOP. ПЕРВАЯ НОЧЬ.",
        announcement_url="https://t.me/rubikub/5158",
        announcement_telegram_ids="*",
        announcement_until=datetime(2026, 8, 6, 3, 0, tzinfo=UTC),  # 6:00 МСК
    )

    late_night = datetime(2026, 8, 6, 2, 59, tzinfo=UTC)
    assert settings.announcement_for(777, now=late_night) is not None

    six_sharp = datetime(2026, 8, 6, 3, 0, tzinfo=UTC)
    assert settings.announcement_for(777, now=six_sharp) is None
    assert settings.announcement_for(777, now=datetime(2026, 8, 6, 9, 0, tzinfo=UTC)) is None

    # Without an hour it simply stays until the text is cleared.
    forever = settings.model_copy(update={"announcement_until": None})
    assert forever.announcement_for(777, now=datetime(2027, 1, 1, tzinfo=UTC)) is not None


def test_a_personal_referral_rate_applies_only_to_whoever_is_named() -> None:
    # Two people were promised ten percent by the owner. Everyone else stays on
    # the standard share, and nothing already accrued is touched: a reward is
    # keyed to the deposit that caused it, and the rate is read when that
    # deposit confirms.
    from app.config import Settings

    settings = Settings(referral_special_bps="630786537:1000, 373473908:1000")

    assert settings.referral_share_bps_for(630786537, 500) == 1000
    assert settings.referral_share_bps_for(373473908, 500) == 1000
    assert settings.referral_share_bps_for(999999999, 500) == 500
    assert settings.referral_share_bps_for(None, 500) == 500

    # Nothing configured means nobody is special.
    assert Settings().referral_share_bps_for(630786537, 500) == 500


def test_a_malformed_personal_rate_is_refused_rather_than_guessed() -> None:
    from app.config import Settings

    for broken in ("630786537:сто", "630786537:20000", "630786537:-5"):
        with pytest.raises(ValueError):
            Settings(referral_special_bps=broken).referral_share_bps_for(630786537, 500)
