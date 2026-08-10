"""Remember the live BANK pulse message pinned in a Telegram chat."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0019"
down_revision: str | None = "20260806_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_chat_state",
        sa.Column("chat_id", sa.BigInteger(), primary_key=True),
        sa.Column("bank_pulse_message_id", sa.BigInteger()),
        sa.Column("bank_pulse_digest", sa.String(length=64)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("telegram_chat_state")
