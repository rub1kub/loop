import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...database import Base, utc_now


def new_id() -> str:
    return str(uuid.uuid4())


class TeamJoinPolicy(enum.StrEnum):
    OPEN = "open"
    REQUEST = "request"
    INVITE = "invite"


class TeamRole(enum.StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        CheckConstraint("state IN ('active', 'archived')", name="team_state"),
        CheckConstraint("join_policy IN ('open', 'request', 'invite')", name="team_join_policy"),
        UniqueConstraint("slug", name="team_slug"),
        UniqueConstraint("tag", name="team_tag"),
        Index("ix_teams_state_created", "state", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    tag: Mapped[str] = mapped_column(String(8), nullable=False)
    mark: Mapped[int] = mapped_column(Integer, nullable=False)
    join_policy: Mapped[str] = mapped_column(
        String(16), default=TeamJoinPolicy.OPEN.value, nullable=False
    )
    state: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TeamMembership(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (
        CheckConstraint("role IN ('owner', 'admin', 'member')", name="team_membership_role"),
        CheckConstraint("state IN ('active', 'left', 'kicked')", name="team_membership_state"),
        Index(
            "uq_team_active_membership_user",
            "user_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
            sqlite_where=text("state = 'active'"),
        ),
        Index(
            "uq_team_active_owner",
            "team_id",
            unique=True,
            postgresql_where=text("state = 'active' AND role = 'owner'"),
            sqlite_where=text("state = 'active' AND role = 'owner'"),
        ),
        Index("ix_team_memberships_team_state", "team_id", "state", "joined_at"),
        Index("ix_team_memberships_user_interval", "user_id", "joined_at", "left_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), default=TeamRole.MEMBER.value, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TeamInvite(Base):
    __tablename__ = "team_invites"
    __table_args__ = (
        UniqueConstraint("token_hash", name="team_invite_token_hash"),
        Index("ix_team_invites_team_active", "team_id", "revoked_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    inviter_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TeamJoinRequest(Base):
    __tablename__ = "team_join_requests"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="team_join_request_state",
        ),
        Index(
            "uq_team_pending_request_user",
            "user_id",
            unique=True,
            postgresql_where=text("state = 'pending'"),
            sqlite_where=text("state = 'pending'"),
        ),
        Index("ix_team_join_requests_team_state", "team_id", "state", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    decided_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TeamSeason(Base):
    __tablename__ = "team_seasons"
    __table_args__ = (
        CheckConstraint("state IN ('active', 'finalizing', 'finalized')", name="team_season_state"),
        CheckConstraint("competition = 'bank_flow'", name="team_season_competition"),
        UniqueConstraint("season_key", name="team_season_key"),
        UniqueConstraint("starts_at", "ends_at", name="team_season_window"),
        Index("ix_team_seasons_window", "starts_at", "ends_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    season_key: Mapped[str] = mapped_column(String(24), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    competition: Mapped[str] = mapped_column(String(24), default="bank_flow", nullable=False)
    formula_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    prize_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TeamScoreEvent(Base):
    __tablename__ = "team_score_events"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('bank_entry', 'bank_payout', 'duel_settlement')",
            name="team_score_event_kind",
        ),
        UniqueConstraint("source_key", name="team_score_event_source"),
        UniqueConstraint(
            "source_kind",
            "source_entity_id",
            "user_id",
            name="team_score_event_entity_user",
        ),
        Index("ix_team_score_events_team_season", "season_id", "team_id", "event_at"),
        Index("ix_team_score_events_user_season", "season_id", "user_id", "event_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    season_id: Mapped[str] = mapped_column(ForeignKey("team_seasons.id"), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    membership_id: Mapped[str] = mapped_column(ForeignKey("team_memberships.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    source_entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_key: Mapped[str] = mapped_column(String(180), nullable=False)
    amount_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    network: Mapped[int] = mapped_column(Integer, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(96), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TeamSeasonStats(Base):
    __tablename__ = "team_season_stats"
    __table_args__ = (
        UniqueConstraint("season_id", "team_id", name="team_season_stats_identity"),
        Index("ix_team_season_stats_rank", "season_id", "flow_nano", "active_members"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    season_id: Mapped[str] = mapped_column(ForeignKey("team_seasons.id"), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    flow_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bank_entries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bank_payouts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duel_settlements: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_members: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class TeamMemberSeasonStats(Base):
    __tablename__ = "team_member_season_stats"
    __table_args__ = (
        UniqueConstraint(
            "season_id", "team_id", "user_id", name="team_member_season_stats_identity"
        ),
        Index("ix_team_member_stats_rank", "season_id", "team_id", "flow_nano"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    season_id: Mapped[str] = mapped_column(ForeignKey("team_seasons.id"), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    flow_nano: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bank_entries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bank_payouts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duel_settlements: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
