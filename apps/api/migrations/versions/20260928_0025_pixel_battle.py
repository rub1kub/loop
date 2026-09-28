"""Add the independent, free pixel battle and its durable audit trail."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260928_0025"
down_revision: str | None = "20260812_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pixel_rounds",
        sa.Column("id", sa.String(10), primary_key=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("pixels", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("revision >= 0", name="pixel_round_revision"),
        sa.CheckConstraint("ends_at > starts_at", name="pixel_round_window"),
    )
    op.create_table(
        "pixel_players",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "pixel_cells",
        sa.Column("round_id", sa.String(10), sa.ForeignKey("pixel_rounds.id"), primary_key=True),
        sa.Column("cell_index", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id")),
        sa.CheckConstraint("cell_index >= 0 AND cell_index < 16384", name="pixel_cell_bounds"),
    )
    op.create_index("ix_pixel_cells_round_team", "pixel_cells", ["round_id", "team_id"])
    op.create_table(
        "pixel_moves",
        sa.Column("round_id", sa.String(10), sa.ForeignKey("pixel_rounds.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("operation_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id")),
        sa.Column("cell_index", sa.Integer(), nullable=False),
        sa.Column("color", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "operation_id", name="pixel_move_once"),
        sa.CheckConstraint("color >= 0 AND color < 16", name="pixel_move_color"),
        sa.CheckConstraint("cell_index >= 0 AND cell_index < 16384", name="pixel_move_bounds"),
    )
    op.create_index("ix_pixel_moves_user_time", "pixel_moves", ["user_id", "created_at"])
    op.create_table(
        "pixel_team_scores",
        sa.Column("round_id", sa.String(10), sa.ForeignKey("pixel_rounds.id"), primary_key=True),
        sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id"), primary_key=True),
        sa.Column("held_pixels", sa.Integer(), nullable=False),
        sa.Column("pixel_ms", sa.BigInteger(), nullable=False),
        sa.Column("accrued_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("held_pixels >= 0", name="pixel_score_held"),
        sa.CheckConstraint("pixel_ms >= 0", name="pixel_score_time"),
    )
    op.create_table(
        "pixel_shares",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("round_id", sa.String(10), sa.ForeignKey("pixel_rounds.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("image", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pixel_shares_user_created", "pixel_shares", ["user_id", "created_at"])
    op.create_table(
        "pixel_moderation",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("round_id", sa.String(10), sa.ForeignKey("pixel_rounds.id"), nullable=False),
        sa.Column("actor_hash", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(160), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    # Only an explicitly requested rollback removes pixel data.
    for table in (
        "pixel_moderation",
        "pixel_shares",
        "pixel_team_scores",
        "pixel_moves",
        "pixel_cells",
        "pixel_players",
        "pixel_rounds",
    ):
        op.drop_table(table)
