"""Let the chain projection record a second position the contract already took.

The unique index said one open position per wallet. The contract says nothing of
the kind: it accepted a second deposit from a wallet that already had an open
position, and on 2026-08-05 the projection tried to write that fact down and was
refused. One rejected row failed the whole worker transaction, so every deposit
and every duel stake stopped being confirmed for everyone, for over an hour.

A database constraint may describe an invariant. This one described a wish. The
product rule survives where it can answer for itself: the position endpoint
still refuses a second open position with a 409, before any money moves.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260805_0017"
down_revision: str | None = "20260805_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTIVE = "current_status IN ('pending_confirmation', 'queued', 'partially_funded', 'completed')"


def upgrade() -> None:
    op.drop_index("uq_active_bank_position_wallet", table_name="bank_positions")
    op.create_index(
        "ix_open_bank_position_wallet",
        "bank_positions",
        ["wallet_id", "network", "contract_address"],
        unique=False,
        postgresql_where=sa.text(ACTIVE),
        sqlite_where=sa.text(ACTIVE),
    )


def downgrade() -> None:
    op.drop_index("ix_open_bank_position_wallet", table_name="bank_positions")
    op.create_index(
        "uq_active_bank_position_wallet",
        "bank_positions",
        ["wallet_id", "network", "contract_address"],
        unique=True,
        postgresql_where=sa.text(ACTIVE),
        sqlite_where=sa.text(ACTIVE),
    )
