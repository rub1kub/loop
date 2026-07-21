import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
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


class OfferState(enum.StrEnum):
    PENDING_FUNDING = "pending_funding"
    OPEN = "open"
    MATCHED = "matched"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REJECTED = "rejected"
    SETTLED = "settled"
    REFUNDED = "refunded"


class DuelState(enum.StrEnum):
    REVEALING = "revealing"
    SETTLED = "settled"
    REFUNDED = "refunded"
    EXPIRED = "expired"


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AuthExchange(Base):
    __tablename__ = "auth_exchanges"

    digest: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    auth_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Wallet(Base):
    __tablename__ = "wallets"
    __table_args__ = (UniqueConstraint("network", "address", name="wallet_network_address"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    address: Mapped[str] = mapped_column(String(68), nullable=False)
    public_key: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BankPosition(Base):
    __tablename__ = "bank_positions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    target_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MatchmakingOffer(Base):
    __tablename__ = "matchmaking_offers"
    __table_args__ = (
        UniqueConstraint("network", "onchain_offer_id", name="offer_network_chain_id"),
        Index(
            "uq_active_offer_wallet",
            "wallet_id",
            unique=True,
            postgresql_where=text("state IN ('pending_funding', 'open', 'matched')"),
            sqlite_where=text("state IN ('pending_funding', 'open', 'matched')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    onchain_offer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_address: Mapped[str] = mapped_column(String(68), nullable=False)
    chance_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    total_pool_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stake_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    commitment_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    counter_offer_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), default=OfferState.PENDING_FUNDING.value, nullable=False, index=True
    )
    revealed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    funding_tx_hash: Mapped[str | None] = mapped_column(String(96))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Duel(Base):
    __tablename__ = "duels"
    __table_args__ = (UniqueConstraint("network", "onchain_duel_id", name="duel_chain_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    onchain_duel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    offer_a_id: Mapped[str] = mapped_column(ForeignKey("matchmaking_offers.id"), nullable=False)
    offer_b_id: Mapped[str] = mapped_column(ForeignKey("matchmaking_offers.id"), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), default=DuelState.REVEALING.value, nullable=False, index=True
    )
    winner_wallet: Mapped[str | None] = mapped_column(String(68))
    reveal_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_tx_hash: Mapped[str | None] = mapped_column(String(96))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InlineInvite(Base):
    __tablename__ = "inline_invites"

    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    creator_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stake_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chance_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ChainEvent(Base):
    __tablename__ = "chain_events"
    __table_args__ = (
        UniqueConstraint("network", "account", "lt", "tx_hash", name="chain_event_identity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    account: Mapped[str] = mapped_column(String(68), nullable=False)
    lt: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(96), nullable=False)
    opcode: Mapped[int | None] = mapped_column(BigInteger)
    body_hash: Mapped[str | None] = mapped_column(String(96))
    applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ChainCheckpoint(Base):
    __tablename__ = "chain_checkpoints"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    last_lt: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
