"""Hold one open BANK position per wallet per contract, not per wallet."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0014"
down_revision: str | None = "20260802_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE = (
    "current_status IN "
    "('pending_confirmation', 'queued', 'partially_funded', 'completed')"
)


def upgrade() -> None:
    op.drop_index("uq_active_bank_position_wallet", table_name="bank_positions")
    op.create_index(
        "uq_active_bank_position_wallet",
        "bank_positions",
        ["wallet_id", "network", "contract_address"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
        sqlite_where=sa.text(ACTIVE),
    )


def downgrade() -> None:
    op.drop_index("uq_active_bank_position_wallet", table_name="bank_positions")
    op.create_index(
        "uq_active_bank_position_wallet",
        "bank_positions",
        ["wallet_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
        sqlite_where=sa.text(ACTIVE),
    )
