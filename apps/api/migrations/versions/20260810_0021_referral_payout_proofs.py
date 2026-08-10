"""Make referral payouts reserved, verifiable and idempotent."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0021"
down_revision: str | None = "20260810_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_open_referral_payout_request", table_name="referral_payout_requests")
    op.add_column("referral_payout_requests", sa.Column("prepared_by_wallet", sa.String(length=68)))
    op.add_column("referral_payout_requests", sa.Column("prepared_at", sa.DateTime(timezone=True)))
    op.add_column("referral_payout_requests", sa.Column("signed_boc", sa.Text()))
    op.create_index(
        "uq_referral_payout_tx_hash",
        "referral_payout_requests",
        ["payout_tx_hash"],
        unique=True,
        postgresql_where=sa.text("payout_tx_hash IS NOT NULL"),
        sqlite_where=sa.text("payout_tx_hash IS NOT NULL"),
    )
    op.create_index(
        "uq_open_referral_payout_request",
        "referral_payout_requests",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('requested', 'prepared')"),
        sqlite_where=sa.text("state IN ('requested', 'prepared')"),
    )

    # A single treasury transaction settles every reward reserved by one
    # request, so the former per-reward unique hash was the wrong invariant.
    with op.batch_alter_table("referral_rewards") as batch:
        batch.drop_constraint("uq_referral_rewards_payout_tx_hash", type_="unique")
        batch.add_column(
            sa.Column(
                "payout_request_id",
                sa.String(length=36),
                sa.ForeignKey("referral_payout_requests.id"),
            )
        )
    op.create_index(
        "ix_referral_rewards_payout_request_id",
        "referral_rewards",
        ["payout_request_id"],
    )
    op.create_index(
        "ix_referral_rewards_payout_tx_hash",
        "referral_rewards",
        ["payout_tx_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_referral_rewards_payout_tx_hash", table_name="referral_rewards")
    op.drop_index("ix_referral_rewards_payout_request_id", table_name="referral_rewards")
    with op.batch_alter_table("referral_rewards") as batch:
        batch.drop_column("payout_request_id")
        batch.create_unique_constraint("uq_referral_rewards_payout_tx_hash", ["payout_tx_hash"])
    op.drop_index("uq_open_referral_payout_request", table_name="referral_payout_requests")
    op.drop_index("uq_referral_payout_tx_hash", table_name="referral_payout_requests")
    op.drop_column("referral_payout_requests", "prepared_at")
    op.drop_column("referral_payout_requests", "signed_boc")
    op.drop_column("referral_payout_requests", "prepared_by_wallet")
    op.create_index(
        "uq_open_referral_payout_request",
        "referral_payout_requests",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("state = 'requested'"),
        sqlite_where=sa.text("state = 'requested'"),
    )
