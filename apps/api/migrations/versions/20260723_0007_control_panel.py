"""Add browser control panel state and audit trail."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0007"
down_revision: str | None = "20260722_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_control",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "maintenance_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("bank_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("duel_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("updated_by_wallet", sa.String(length=68), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_control")),
    )
    op.create_table(
        "contract_control",
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("address", sa.String(length=68), nullable=False),
        sa.Column("owner", sa.String(length=68), nullable=False),
        sa.Column("treasury", sa.String(length=68), nullable=False),
        sa.Column("fee_bps", sa.Integer(), nullable=False),
        sa.Column("paused", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("locked_nano", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_tx_hash", sa.String(length=96), nullable=True),
        sa.Column("last_lt", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_contract_control")),
    )
    op.create_table(
        "admin_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("wallet", sa.String(length=68), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=160), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("tx_hash", sa.String(length=96), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_events")),
    )
    op.create_index(
        op.f("ix_admin_audit_events_wallet"),
        "admin_audit_events",
        ["wallet"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_admin_audit_events_wallet"), table_name="admin_audit_events")
    op.drop_table("admin_audit_events")
    op.drop_table("contract_control")
    op.drop_table("application_control")
