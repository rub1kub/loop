"""Carry the inviter's GRAM share of each referred deposit's fee."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0015"
down_revision: str | None = "20260802_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "referral_rewards",
        sa.Column("reward_nano", sa.BigInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("referral_rewards", "reward_nano")
