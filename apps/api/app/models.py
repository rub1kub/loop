import enum
import secrets
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, utc_now


def new_id() -> str:
    return str(uuid.uuid4())


def new_public_id() -> str:
    return secrets.token_urlsafe(18)


class ProofType(enum.StrEnum):
    SYSTEM = "system"
    TELEGRAM = "telegram"
    TON_TRANSACTION = "ton_transaction"
    TON_STATE = "ton_state"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(16))
    photo_url: Mapped[str | None] = mapped_column(Text)
    referred_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    onboarding_seen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarding_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    result_notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ResultCard(Base):
    __tablename__ = "result_cards"
    __table_args__ = (
        UniqueConstraint("event_key", name="result_card_event_once"),
        UniqueConstraint("public_id", name="result_card_public_id"),
        CheckConstraint("mode IN ('bank', 'duel', 'bank_entry')", name="result_card_mode"),
        CheckConstraint("payout_nano >= 0", name="result_card_payout"),
        CheckConstraint("contributed_nano >= 0", name="result_card_contributed"),
        CheckConstraint(
            "(mode = 'bank_entry' AND result_nano = 0 AND payout_nano = 0)"
            " OR (mode <> 'bank_entry' AND result_nano > 0)",
            name="result_card_positive",
        ),
        Index("ix_result_cards_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(32), default=new_public_id, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_key: Mapped[str] = mapped_column(String(180), nullable=False)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    payout_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    contributed_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    result_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(96), nullable=False)
    proof_url: Mapped[str] = mapped_column(Text, nullable=False)
    queue_position: Mapped[int | None] = mapped_column(Integer)
    template_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    share_prepared_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="notification_dedupe_once"),
        CheckConstraint(
            "state IN ('pending', 'processing', 'retry', 'sent', 'blocked', 'failed')",
            name="notification_state",
        ),
        CheckConstraint(
            "kind IN ('result', 'duel_matched', 'referral_qualified', "
            "'duel_reveal_soon', 'public_feed')",
            name="notification_kind",
        ),
        Index("ix_notification_outbox_due", "state", "next_attempt_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), default="result", nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(180), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_card_id: Mapped[str | None] = mapped_column(ForeignKey("result_cards.id"))
    state: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(String(64))
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthExchange(Base):
    __tablename__ = "auth_exchanges"
    digest: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    auth_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("network", "address", name="wallet_network_address"),
        Index(
            "uq_active_wallet_user",
            "user_id",
            unique=True,
            postgresql_where=text("active = true"),
            sqlite_where=text("active = 1"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    address: Mapped[str] = mapped_column(String(68), nullable=False)
    public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ReferralCode(Base):
    __tablename__ = "referral_codes"
    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReferralAttribution(Base):
    __tablename__ = "referral_attributions"
    __table_args__ = (
        UniqueConstraint("invitee_user_id", name="referral_invitee_once"),
        UniqueConstraint("inviter_user_id", "invitee_user_id", name="referral_edge_once"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    inviter_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    invitee_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(ForeignKey("referral_codes.code"), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    qualified_tx_hash: Mapped[str | None] = mapped_column(String(96))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReferralReward(Base):
    __tablename__ = "referral_rewards"
    __table_args__ = (UniqueConstraint("attribution_id", "cause", name="referral_reward_cause"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    attribution_id: Mapped[str] = mapped_column(
        ForeignKey("referral_attributions.id"), nullable=False, index=True
    )
    cause: Mapped[str] = mapped_column(String(64), nullable=False)
    reward_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # The inviter's share of the fee from one confirmed deposit, in nanoGRAM.
    # Accrued here, paid from the treasury; payout_tx_hash закрывает строку.
    reward_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    payout_tx_hash: Mapped[str | None] = mapped_column(String(96), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ReferralPayoutRequest(Base):
    """Кто, сколько и на какой кошелёк просит вывести с рефералки.

    Выплата остаётся ручной: строка здесь фиксирует просьбу и её сумму на
    момент подачи, а деньги отправляет владелец. Пока заявка открыта, вторую
    подать нельзя — иначе одна и та же сумма попросилась бы дважды.
    """

    __tablename__ = "referral_payout_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    address: Mapped[str] = mapped_column(String(68), nullable=False)
    amount_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="requested", nullable=False)
    payout_tx_hash: Mapped[str | None] = mapped_column(String(96))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChainCheckpoint(Base):
    __tablename__ = "chain_checkpoints"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_lt: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ApplicationControl(Base):
    __tablename__ = "application_control"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    maintenance_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bank_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    duel_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by_wallet: Mapped[str | None] = mapped_column(String(68))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ContractControl(Base):
    __tablename__ = "contract_control"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    address: Mapped[str] = mapped_column(String(68), nullable=False)
    owner: Mapped[str] = mapped_column(String(68), nullable=False)
    treasury: Mapped[str] = mapped_column(String(68), nullable=False)
    fee_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    paused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_tx_hash: Mapped[str | None] = mapped_column(String(96))
    last_lt: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    wallet: Mapped[str] = mapped_column(String(68), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="prepared", nullable=False)
    tx_hash: Mapped[str | None] = mapped_column(String(96))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


# Register bounded-context tables in the shared SQLAlchemy metadata.
from .modules.bank import models as _bank_models  # noqa: E402,F401
from .modules.duel import models as _duel_models  # noqa: E402,F401
