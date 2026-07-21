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
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...database import Base, utc_now


def new_id() -> str:
    return str(uuid.uuid4())


class OfferState(enum.StrEnum):
    PENDING_FUNDING = "pending_funding"
    OPEN = "open"
    RESERVED = "reserved"
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


class ChallengeState(enum.StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    FUNDING = "funding"
    MATCHED = "matched"
    EXPIRED = "expired"


class DuelOffer(Base):
    __tablename__ = "duel_offers"
    __table_args__ = (
        UniqueConstraint("network", "onchain_offer_id", name="duel_offer_network_chain_id"),
        UniqueConstraint("network", "query_id", name="duel_offer_query_id"),
        Index(
            "uq_active_duel_offer_wallet",
            "wallet_id",
            unique=True,
            postgresql_where=text("state IN ('pending_funding', 'open', 'reserved', 'matched')"),
            sqlite_where=text("state IN ('pending_funding', 'open', 'reserved', 'matched')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    onchain_offer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    query_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    wallet_id: Mapped[str | None] = mapped_column(ForeignKey("wallets.id"), index=True)
    owner_wallet: Mapped[str] = mapped_column(String(68), nullable=False)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_address: Mapped[str] = mapped_column(String(68), nullable=False)
    chance_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    total_pool_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stake_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    opponent_stake_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    payout_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    commitment_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    counter_offer_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="afk", nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), default=OfferState.PENDING_FUNDING.value, nullable=False, index=True
    )
    revealed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reserved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    funding_tx_hash: Mapped[str | None] = mapped_column(String(96))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Duel(Base):
    __tablename__ = "duels"
    __table_args__ = (
        UniqueConstraint("network", "onchain_duel_id", name="duel_chain_id"),
        Index("ix_loop_duels_state", "state"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    onchain_duel_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    offer_a_id: Mapped[str] = mapped_column(ForeignKey("duel_offers.id"), nullable=False)
    offer_b_id: Mapped[str] = mapped_column(ForeignKey("duel_offers.id"), nullable=False)
    state: Mapped[str] = mapped_column(
        String(24), default=DuelState.REVEALING.value, nullable=False
    )
    winner_wallet: Mapped[str | None] = mapped_column(String(68))
    reveal_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_tx_hash: Mapped[str | None] = mapped_column(String(96))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DuelPlayer(Base):
    __tablename__ = "duel_players"
    __table_args__ = (UniqueConstraint("duel_id", "wallet_id", name="duel_player_wallet"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    duel_id: Mapped[str] = mapped_column(ForeignKey("duels.id"), nullable=False, index=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("duel_offers.id"), nullable=False, unique=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    wallet_id: Mapped[str | None] = mapped_column(ForeignKey("wallets.id"))
    chance_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    stake_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)


class DuelCommit(Base):
    __tablename__ = "duel_commits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    offer_id: Mapped[str] = mapped_column(ForeignKey("duel_offers.id"), nullable=False, unique=True)
    commitment_hex: Mapped[str] = mapped_column(String(64), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DuelReveal(Base):
    __tablename__ = "duel_reveals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    duel_id: Mapped[str] = mapped_column(ForeignKey("duels.id"), nullable=False, index=True)
    offer_id: Mapped[str] = mapped_column(ForeignKey("duel_offers.id"), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DuelSettlement(Base):
    __tablename__ = "duel_settlements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    duel_id: Mapped[str] = mapped_column(ForeignKey("duels.id"), nullable=False, unique=True)
    winner_wallet: Mapped[str | None] = mapped_column(String(68))
    payout_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_nano: Mapped[int] = mapped_column(BigInteger, nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DuelChainEvent(Base):
    __tablename__ = "duel_chain_events"
    __table_args__ = (
        UniqueConstraint(
            "network", "account", "lt", "tx_hash", "event_index", name="duel_chain_event_identity"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    account: Mapped[str] = mapped_column(String(68), nullable=False)
    lt: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(96), nullable=False)
    event_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opcode: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    applied: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class DuelInvitation(Base):
    __tablename__ = "duel_invitations"
    __table_args__ = (
        UniqueConstraint("creator_offer_id", name="duel_invitation_offer"),
        Index("ix_duel_invitations_state_expires", "state", "expires_at"),
    )
    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    creator_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    creator_offer_id: Mapped[str] = mapped_column(ForeignKey("duel_offers.id"), nullable=False)
    accepted_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    state: Mapped[str] = mapped_column(
        String(24), default=ChallengeState.OPEN.value, nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


MatchmakingOffer = DuelOffer
DuelChallenge = DuelInvitation
