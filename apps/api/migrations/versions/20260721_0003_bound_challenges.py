"""Bind Telegram challenges to funded on-chain offers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0003"
down_revision: str | None = "20260721_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "duel_challenges",
        sa.Column("code", sa.String(length=24), nullable=False),
        sa.Column("creator_user_id", sa.String(length=36), nullable=False),
        sa.Column("creator_offer_id", sa.String(length=36), nullable=False),
        sa.Column("accepted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("state", sa.String(length=24), server_default="open", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
            name="fk_duel_challenges_accepted_by_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["creator_offer_id"],
            ["matchmaking_offers.id"],
            name="fk_duel_challenges_creator_offer_id_matchmaking_offers",
        ),
        sa.ForeignKeyConstraint(
            ["creator_user_id"],
            ["users.id"],
            name="fk_duel_challenges_creator_user_id_users",
        ),
        sa.PrimaryKeyConstraint("code", name="pk_duel_challenges"),
        sa.UniqueConstraint("creator_offer_id", name="duel_challenge_offer"),
    )
    op.create_index(
        "ix_duel_challenges_accepted_by_user_id",
        "duel_challenges",
        ["accepted_by_user_id"],
        unique=False,
    )
    op.create_index("ix_duel_challenges_creator_user_id", "duel_challenges", ["creator_user_id"])
    op.create_index("ix_duel_challenges_state", "duel_challenges", ["state"])
    op.create_index(
        "ix_duel_challenges_state_expires",
        "duel_challenges",
        ["state", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_duel_challenges_state_expires", table_name="duel_challenges")
    op.drop_index("ix_duel_challenges_state", table_name="duel_challenges")
    op.drop_index("ix_duel_challenges_creator_user_id", table_name="duel_challenges")
    op.drop_index("ix_duel_challenges_accepted_by_user_id", table_name="duel_challenges")
    op.drop_table("duel_challenges")
