import secrets
from functools import lru_cache
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LOOP_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "LOOP"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://loop:loop@localhost:5432/loop"
    redis_url: str = "redis://localhost:6379/0"
    auto_create_schema: bool = False

    bot_token: SecretStr = SecretStr("")
    bot_username: str = ""
    telegram_webhook_secret: SecretStr = SecretStr("")
    telegram_auth_max_age_seconds: int = 21_600
    telegram_future_skew_seconds: int = 30

    session_secret: SecretStr = SecretStr("development-only-change-me")
    session_ttl_seconds: int = 21_600
    control_admin_wallet: str = ""
    control_session_ttl_seconds: int = 3_600
    public_origin: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"

    ton_network_id: int = -3
    toncenter_url: str = "https://testnet.toncenter.com"
    toncenter_api_key: SecretStr = SecretStr("")
    bank_contract_address: str = ""
    bank_contract_code_hash: str = ""
    bank_fee_bps: int = 100
    bank_position_gas_nano: int = 80_000_000
    bank_min_principal_nano: int = 1_000_000_000
    bank_max_principal_nano: int = 100_000_000_000
    duel_contract_address: str = ""
    duel_contract_code_hash: str = ""
    duel_fee_bps: int = 250
    duel_invite_signing_key: SecretStr = SecretStr("")
    duel_invite_public_key: str = ""
    # Legacy names are read during the one-release migration window.
    ton_contract_address: str = ""
    ton_contract_code_hash: str = ""
    ton_proof_ttl_seconds: int = 300
    offer_ttl_seconds: int = 900
    reveal_ttl_seconds: int = 300
    offer_gas_nano: int = 50_000_000
    min_pool_nano: int = 1_000_000_000
    max_pool_nano: int = 100_000_000_000
    fee_bps: int = 250

    plush_brick_master: str = "EQAJ40p3zlCoomgANMQ4u5eIktLMZtWP87GGKDKlyW_EZBwt"
    plush_brick_network_id: int = -239
    plush_brick_toncenter_url: str = "https://toncenter.com"
    holder_min_balance_nano: int = 1
    plush_brick_fee_bps: int = 0

    webhook_path: str = "/api/internal/telegram/webhook"
    metrics_token: SecretStr = SecretStr("")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def effective_duel_contract_address(self) -> str:
        return self.duel_contract_address or self.ton_contract_address

    @property
    def effective_duel_contract_code_hash(self) -> str:
        return self.duel_contract_code_hash or self.ton_contract_code_hash

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.app_env != "production":
            return self
        required = {
            "LOOP_BOT_TOKEN": self.bot_token.get_secret_value(),
            "LOOP_BOT_USERNAME": self.bot_username,
            "LOOP_TELEGRAM_WEBHOOK_SECRET": self.telegram_webhook_secret.get_secret_value(),
            "LOOP_SESSION_SECRET": self.session_secret.get_secret_value(),
            "LOOP_BANK_CONTRACT_ADDRESS": self.bank_contract_address,
            "LOOP_BANK_CONTRACT_CODE_HASH": self.bank_contract_code_hash,
            "LOOP_DUEL_CONTRACT_ADDRESS": self.effective_duel_contract_address,
            "LOOP_DUEL_CONTRACT_CODE_HASH": self.effective_duel_contract_code_hash,
            "LOOP_DUEL_INVITE_SIGNING_KEY": self.duel_invite_signing_key.get_secret_value(),
            "LOOP_DUEL_INVITE_PUBLIC_KEY": self.duel_invite_public_key,
            "LOOP_METRICS_TOKEN": self.metrics_token.get_secret_value(),
            "LOOP_CONTROL_ADMIN_WALLET": self.control_admin_wallet,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"missing production settings: {', '.join(missing)}")
        if not self.public_origin.startswith("https://"):
            raise ValueError("production public origin must use HTTPS")
        if self.session_secret.get_secret_value() == "development-only-change-me":
            raise ValueError("production session secret is unsafe")
        if (
            min(
                len(self.session_secret.get_secret_value()),
                len(self.telegram_webhook_secret.get_secret_value()),
                len(self.metrics_token.get_secret_value()),
            )
            < 32
        ):
            raise ValueError("production secrets must be at least 32 characters")
        try:
            hashes = (
                self.bank_contract_code_hash,
                self.effective_duel_contract_code_hash,
            )
            if any(len(bytes.fromhex(value.removeprefix("0x"))) != 32 for value in hashes):
                raise ValueError
        except ValueError as exc:
            raise ValueError("TON contract code hashes must be 32-byte hex") from exc
        try:
            seed = bytes.fromhex(self.duel_invite_signing_key.get_secret_value())
            configured_public_key = bytes.fromhex(self.duel_invite_public_key)
            derived_public_key = (
                Ed25519PrivateKey.from_private_bytes(seed)
                .public_key()
                .public_bytes(Encoding.Raw, PublicFormat.Raw)
            )
            if len(seed) != 32 or len(configured_public_key) != 32 or not secrets.compare_digest(
                derived_public_key, configured_public_key
            ):
                raise ValueError
        except ValueError as exc:
            raise ValueError("DUEL invite signing key pair is invalid") from exc
        if self.ton_network_id != -3:
            raise ValueError("mainnet is disabled until the documented release gate is complete")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
