"""Add unlimited teams, temporal membership and proof-backed weekly competition."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0020"
down_revision: str | None = "20260810_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("slug", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=160), nullable=False),
        sa.Column("tag", sa.String(length=8), nullable=False),
        sa.Column("mark", sa.Integer(), nullable=False),
        sa.Column("join_policy", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("state IN ('active', 'archived')", name="team_state"),
        sa.CheckConstraint("join_policy IN ('open', 'request', 'invite')", name="team_join_policy"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.UniqueConstraint("slug", name="team_slug"),
        sa.UniqueConstraint("tag", name="team_tag"),
    )
    op.create_index("ix_teams_owner_user_id", "teams", ["owner_user_id"])
    op.create_index("ix_teams_state_created", "teams", ["state", "created_at"])

    op.create_table(
        "team_memberships",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('owner', 'admin', 'member')", name="team_membership_role"),
        sa.CheckConstraint("state IN ('active', 'left', 'kicked')", name="team_membership_state"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_team_memberships_team_id", "team_memberships", ["team_id"])
    op.create_index("ix_team_memberships_user_id", "team_memberships", ["user_id"])
    op.create_index(
        "ix_team_memberships_team_state",
        "team_memberships",
        ["team_id", "state", "joined_at"],
    )
    op.create_index(
        "ix_team_memberships_user_interval",
        "team_memberships",
        ["user_id", "joined_at", "left_at"],
    )
    op.create_index(
        "uq_team_active_membership_user",
        "team_memberships",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
        sqlite_where=sa.text("state = 'active'"),
    )
    op.create_index(
        "uq_team_active_owner",
        "team_memberships",
        ["team_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active' AND role = 'owner'"),
        sqlite_where=sa.text("state = 'active' AND role = 'owner'"),
    )

    op.create_table(
        "team_invites",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("inviter_user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["inviter_user_id"], ["users.id"]),
        sa.UniqueConstraint("token_hash", name="team_invite_token_hash"),
    )
    op.create_index("ix_team_invites_team_id", "team_invites", ["team_id"])
    op.create_index(
        "ix_team_invites_team_active",
        "team_invites",
        ["team_id", "revoked_at", "expires_at"],
    )

    op.create_table(
        "team_join_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("decided_by_user_id", sa.String(length=36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="team_join_request_state",
        ),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"]),
    )
    op.create_index("ix_team_join_requests_team_id", "team_join_requests", ["team_id"])
    op.create_index("ix_team_join_requests_user_id", "team_join_requests", ["user_id"])
    op.create_index(
        "ix_team_join_requests_team_state",
        "team_join_requests",
        ["team_id", "state", "created_at"],
    )
    op.create_index(
        "uq_team_pending_request_user",
        "team_join_requests",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("state = 'pending'"),
        sqlite_where=sa.text("state = 'pending'"),
    )

    op.create_table(
        "team_seasons",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("season_key", sa.String(length=24), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("competition", sa.String(length=24), nullable=False),
        sa.Column("formula_version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("prize_nano", sa.BigInteger(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('active', 'finalizing', 'finalized')", name="team_season_state"
        ),
        sa.CheckConstraint("competition = 'bank_flow'", name="team_season_competition"),
        sa.UniqueConstraint("season_key", name="team_season_key"),
        sa.UniqueConstraint("starts_at", "ends_at", name="team_season_window"),
    )
    op.create_index("ix_team_seasons_window", "team_seasons", ["starts_at", "ends_at"])

    op.create_table(
        "team_score_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("season_id", sa.String(length=36), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("membership_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("source_kind", sa.String(length=24), nullable=False),
        sa.Column("source_entity_id", sa.String(length=36), nullable=False),
        sa.Column("source_key", sa.String(length=180), nullable=False),
        sa.Column("amount_nano", sa.BigInteger(), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("tx_hash", sa.String(length=96), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('bank_entry', 'bank_payout', 'duel_settlement')",
            name="team_score_event_kind",
        ),
        sa.ForeignKeyConstraint(["season_id"], ["team_seasons.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["membership_id"], ["team_memberships.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("source_key", name="team_score_event_source"),
        sa.UniqueConstraint(
            "source_kind",
            "source_entity_id",
            "user_id",
            name="team_score_event_entity_user",
        ),
    )
    op.create_index(
        "ix_team_score_events_team_season",
        "team_score_events",
        ["season_id", "team_id", "event_at"],
    )
    op.create_index(
        "ix_team_score_events_user_season",
        "team_score_events",
        ["season_id", "user_id", "event_at"],
    )

    op.create_table(
        "team_season_stats",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("season_id", sa.String(length=36), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("flow_nano", sa.BigInteger(), nullable=False),
        sa.Column("bank_entries", sa.Integer(), nullable=False),
        sa.Column("bank_payouts", sa.Integer(), nullable=False),
        sa.Column("duel_settlements", sa.Integer(), nullable=False),
        sa.Column("active_members", sa.Integer(), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["season_id"], ["team_seasons.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.UniqueConstraint("season_id", "team_id", name="team_season_stats_identity"),
    )
    op.create_index(
        "ix_team_season_stats_rank",
        "team_season_stats",
        ["season_id", "flow_nano", "active_members"],
    )

    op.create_table(
        "team_member_season_stats",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("season_id", sa.String(length=36), nullable=False),
        sa.Column("team_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("flow_nano", sa.BigInteger(), nullable=False),
        sa.Column("bank_entries", sa.Integer(), nullable=False),
        sa.Column("bank_payouts", sa.Integer(), nullable=False),
        sa.Column("duel_settlements", sa.Integer(), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["season_id"], ["team_seasons.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "season_id", "team_id", "user_id", name="team_member_season_stats_identity"
        ),
    )
    op.create_index(
        "ix_team_member_stats_rank",
        "team_member_season_stats",
        ["season_id", "team_id", "flow_nano"],
    )


def downgrade() -> None:
    op.drop_table("team_member_season_stats")
    op.drop_table("team_season_stats")
    op.drop_table("team_score_events")
    op.drop_table("team_seasons")
    op.drop_table("team_join_requests")
    op.drop_table("team_invites")
    op.drop_table("team_memberships")
    op.drop_table("teams")
