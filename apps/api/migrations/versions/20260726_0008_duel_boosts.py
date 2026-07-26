"""Add DUEL boost window projection."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0008"
down_revision: str | None = "20260723_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("duels") as batch:
        batch.add_column(sa.Column("boost_deadline", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("hard_deadline", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("boost_revision", sa.Integer(), server_default="0", nullable=False)
        )

    op.create_table(
        "duel_boosts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("duel_id", sa.String(length=36), nullable=False),
        sa.Column("offer_id", sa.String(length=36), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("query_id", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("amount_nano", sa.BigInteger(), nullable=False),
        sa.Column("chance_a_bps", sa.Integer(), nullable=False),
        sa.Column("chance_b_bps", sa.Integer(), nullable=False),
        sa.Column("tx_hash", sa.String(length=96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["duel_id"],
            ["duels.id"],
            name=op.f("fk_duel_boosts_duel_id_duels"),
        ),
        sa.ForeignKeyConstraint(
            ["offer_id"], ["duel_offers.id"], name=op.f("fk_duel_boosts_offer_id_duel_offers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_duel_boosts")),
        sa.UniqueConstraint("network", "tx_hash", name="duel_boost_chain_id"),
        sa.UniqueConstraint("duel_id", "revision", name="duel_boost_revision"),
    )
    op.create_index(
        "ix_duel_boosts_duel_created",
        "duel_boosts",
        ["duel_id", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_duel_boosts_duel_id"), "duel_boosts", ["duel_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_duel_boosts_duel_id"), table_name="duel_boosts")
    op.drop_index("ix_duel_boosts_duel_created", table_name="duel_boosts")
    op.drop_table("duel_boosts")
    with op.batch_alter_table("duels") as batch:
        batch.drop_column("boost_revision")
        batch.drop_column("hard_deadline")
        batch.drop_column("boost_deadline")
