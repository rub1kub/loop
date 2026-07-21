"""Add BANK social cycles and proof-backed event history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0002"
down_revision: str | None = "20260721_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_cycles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("goal_events", sa.Integer(), server_default="6", nullable=False),
        sa.Column("event_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_bank_cycles_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_bank_cycles"),
        sa.UniqueConstraint(
            "user_id", "sequence_number", name="bank_cycle_user_sequence"
        ),
    )
    op.create_index("ix_bank_cycles_status", "bank_cycles", ["status"], unique=False)
    op.create_index("ix_bank_cycles_user_id", "bank_cycles", ["user_id"], unique=False)
    op.create_index(
        "uq_active_bank_cycle_user",
        "bank_cycles",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "cycle_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("cycle_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("proof_type", sa.String(length=32), nullable=False),
        sa.Column("proof_ref", sa.String(length=160), nullable=True),
        sa.Column("dedupe_key", sa.String(length=192), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_cycle_events_actor_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["cycle_id"], ["bank_cycles.id"], name="fk_cycle_events_cycle_id_bank_cycles"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_cycle_events_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cycle_events"),
        sa.UniqueConstraint("cycle_id", "dedupe_key", name="cycle_event_dedupe"),
    )
    op.create_index("ix_cycle_events_cycle_id", "cycle_events", ["cycle_id"], unique=False)
    op.create_index("ix_cycle_events_kind", "cycle_events", ["kind"], unique=False)
    op.create_index("ix_cycle_events_user_id", "cycle_events", ["user_id"], unique=False)
    op.create_index(
        "ix_cycle_events_user_created",
        "cycle_events",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cycle_events_user_created", table_name="cycle_events")
    op.drop_index("ix_cycle_events_user_id", table_name="cycle_events")
    op.drop_index("ix_cycle_events_kind", table_name="cycle_events")
    op.drop_index("ix_cycle_events_cycle_id", table_name="cycle_events")
    op.drop_table("cycle_events")
    op.drop_index("uq_active_bank_cycle_user", table_name="bank_cycles")
    op.drop_index("ix_bank_cycles_user_id", table_name="bank_cycles")
    op.drop_index("ix_bank_cycles_status", table_name="bank_cycles")
    op.drop_table("bank_cycles")
