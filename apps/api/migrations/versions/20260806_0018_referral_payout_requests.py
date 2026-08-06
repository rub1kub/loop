"""Record who asked to be paid their referral share, and where to.

Paying stays manual — the owner sends it from the treasury. What was missing
was the asking: people earned, saw the figure, and had nowhere to say "send it
to this wallet" except the chat.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_0018"
down_revision: str | None = "20260805_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "referral_payout_requests",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("address", sa.String(length=68), nullable=False),
        sa.Column("amount_nano", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="requested"),
        sa.Column("payout_tx_hash", sa.String(length=96)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
    )
    # One open request per person: a second would ask for the same money twice.
    op.create_index(
        "uq_open_referral_payout_request",
        "referral_payout_requests",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("state = 'requested'"),
        sqlite_where=sa.text("state = 'requested'"),
    )


def downgrade() -> None:
    op.drop_index("uq_open_referral_payout_request", table_name="referral_payout_requests")
    op.drop_table("referral_payout_requests")
