"""Track the on-chain PLUSH BRICK holder fee exemption per DUEL offer."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0010"
down_revision: str | None = "20260726_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("duel_offers") as batch:
        batch.add_column(
            sa.Column(
                "fee_exempt",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("duel_offers") as batch:
        batch.drop_column("fee_exempt")
