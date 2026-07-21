import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...database import Base, utc_now


def new_id() -> str:
    return str(uuid.uuid4())


class BankPositionStatus(enum.StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    QUEUED = "queued"
    PARTIALLY_FUNDED = "partially_funded"
    COMPLETED = "completed"
    PAYOUT_SENT = "payout_sent"
    FAILED = "failed"


class BankPosition(Base):
    __tablename__ = "bank_positions"
    __table_args__ = (
        UniqueConstraint(
            "network", "contract_address", "position_id", name="bank_position_chain_id"
        ),
        UniqueConstraint("network", "contract_address", "query_id", name="bank_position_query_id"),
        Index(
            "uq_active_bank_position_wallet",
            "wallet_id",
            unique=True,
            postgresql_where=text(
                "current_status IN "
                "('pending_confirmation', 'queued', 'partially_funded', 'completed')"
            ),
            sqlite_where=text(
                "current_status IN "
                "('pending_confirmation', 'queued', 'partially_funded', 'completed')"
            ),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    position_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    wallet_id: Mapped[str | None] = mapped_column(ForeignKey("wallets.id"), index=True)
    owner_wallet: Mapped[str] = mapped_column(String(68), nullable=False)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_address: Mapped[str] = mapped_column(String(68), nullable=False)
    query_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    principal_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    multiplier_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    target_payout_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    funded_amount_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    remaining_amount_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    queue_index: Mapped[int | None] = mapped_column(BigInteger)
    current_status: Mapped[str] = mapped_column(
        String(32),
        default=BankPositionStatus.PENDING_CONFIRMATION.value,
        nullable=False,
        index=True,
    )
    funding_transaction: Mapped[str | None] = mapped_column(String(96))
    payout_transaction: Mapped[str | None] = mapped_column(String(96))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BankPayout(Base):
    __tablename__ = "bank_payouts"
    __table_args__ = (
        UniqueConstraint("position_id", name="bank_payout_position_once"),
        UniqueConstraint("network", "tx_hash", "position_id", name="bank_payout_chain_id"),
        Index("ix_bank_payouts_position_id", "position_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    position_id: Mapped[str] = mapped_column(ForeignKey("bank_positions.id"), nullable=False)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    destination: Mapped[str] = mapped_column(String(68), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(96), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class BankChainEvent(Base):
    __tablename__ = "bank_chain_events"
    __table_args__ = (
        UniqueConstraint(
            "network", "account", "lt", "tx_hash", "event_index", name="bank_chain_event_identity"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    account: Mapped[str] = mapped_column(String(68), nullable=False)
    lt: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(96), nullable=False)
    event_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opcode: Mapped[int] = mapped_column(BigInteger, nullable=False)
    position_id: Mapped[int | None] = mapped_column(BigInteger)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    applied: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
