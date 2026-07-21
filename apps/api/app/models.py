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


class CycleStatus(enum.StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"


class CycleEventKind(enum.StrEnum):
    CYCLE_STARTED = "cycle_started"
    INVITE_CREATED = "invite_created"
    INVITE_ACCEPTED = "invite_accepted"
    DUEL_FUNDED = "duel_funded"
    DUEL_MATCHED = "duel_matched"
    DUEL_SETTLED = "duel_settled"
    DUEL_REFUNDED = "duel_refunded"
    ASSET_VERIFIED = "asset_verified"


class ProofType(enum.StrEnum):
    SYSTEM = "system"
    TELEGRAM = "telegram"
    TON_TRANSACTION = "ton_transaction"
    TON_STATE = "ton_state"


class ChallengeState(enum.StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    FUNDING = "funding"
    MATCHED = "matched"
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
    """Legacy wallet-goal record kept for rollback compatibility.

    LOOP no longer reads or writes this model. Production data is intentionally
    retained while the social cycle model proves stable.
    """

    __tablename__ = "bank_positions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    target_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class BankCycle(Base):
    __tablename__ = "bank_cycles"
    __table_args__ = (
        UniqueConstraint("user_id", "sequence_number", name="bank_cycle_user_sequence"),
        Index(
            "uq_active_bank_cycle_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), default=CycleStatus.ACTIVE.value, nullable=False, index=True
    )
    goal_events: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CycleEvent(Base):
    __tablename__ = "cycle_events"
    __table_args__ = (
        UniqueConstraint("cycle_id", "dedupe_key", name="cycle_event_dedupe"),
        Index("ix_cycle_events_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("bank_cycles.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    proof_type: Mapped[str] = mapped_column(String(32), nullable=False)
    proof_ref: Mapped[str | None] = mapped_column(String(160))
    dedupe_key: Mapped[str] = mapped_column(String(192), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


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
    """Legacy unbound inline invite retained for rollback compatibility."""

    __tablename__ = "inline_invites"

    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    creator_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stake_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chance_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DuelChallenge(Base):
    __tablename__ = "duel_challenges"
    __table_args__ = (
        UniqueConstraint("creator_offer_id", name="duel_challenge_offer"),
        Index("ix_duel_challenges_state_expires", "state", "expires_at"),
    )

    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    creator_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    creator_offer_id: Mapped[str] = mapped_column(
        ForeignKey("matchmaking_offers.id"), nullable=False
    )
    accepted_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    state: Mapped[str] = mapped_column(
        String(24), default=ChallengeState.OPEN.value, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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
