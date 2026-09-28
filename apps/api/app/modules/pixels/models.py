from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ...database import Base, utc_now


class PixelRound(Base):
    __tablename__ = "pixel_rounds"
    __table_args__ = (
        CheckConstraint("revision >= 0", name="pixel_round_revision"),
        CheckConstraint("ends_at > starts_at", name="pixel_round_window"),
    )

    id: Mapped[str] = mapped_column(String(10), primary_key=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Pixels and revision are one row: a snapshot cannot mix two revisions.
    pixels: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class PixelPlayer(Base):
    __tablename__ = "pixel_players"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PixelCell(Base):
    __tablename__ = "pixel_cells"
    __table_args__ = (
        CheckConstraint("cell_index >= 0 AND cell_index < 16384", name="pixel_cell_bounds"),
        Index("ix_pixel_cells_round_team", "round_id", "team_id"),
    )

    round_id: Mapped[str] = mapped_column(ForeignKey("pixel_rounds.id"), primary_key=True)
    cell_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))


class PixelMove(Base):
    __tablename__ = "pixel_moves"
    __table_args__ = (
        UniqueConstraint("user_id", "operation_id", name="pixel_move_once"),
        CheckConstraint("color >= 0 AND color < 16", name="pixel_move_color"),
        CheckConstraint("cell_index >= 0 AND cell_index < 16384", name="pixel_move_bounds"),
        Index("ix_pixel_moves_user_time", "user_id", "created_at"),
    )

    round_id: Mapped[str] = mapped_column(ForeignKey("pixel_rounds.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    cell_index: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PixelTeamScore(Base):
    __tablename__ = "pixel_team_scores"
    __table_args__ = (
        CheckConstraint("held_pixels >= 0", name="pixel_score_held"),
        CheckConstraint("pixel_ms >= 0", name="pixel_score_time"),
    )

    round_id: Mapped[str] = mapped_column(ForeignKey("pixel_rounds.id"), primary_key=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    held_pixels: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pixel_ms: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    accrued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PixelShare(Base):
    __tablename__ = "pixel_shares"
    __table_args__ = (Index("ix_pixel_shares_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    round_id: Mapped[str] = mapped_column(ForeignKey("pixel_rounds.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    image: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PixelModeration(Base):
    __tablename__ = "pixel_moderation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    round_id: Mapped[str] = mapped_column(ForeignKey("pixel_rounds.id"), nullable=False)
    actor_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(160), nullable=False)
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
