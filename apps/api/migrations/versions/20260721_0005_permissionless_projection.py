"""Allow projections of permissionless BANK and DUEL participants."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260721_0005"
down_revision: str | None = "20260721_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("bank_positions") as batch:
        batch.alter_column("user_id", nullable=True)
        batch.alter_column("wallet_id", nullable=True)
    with op.batch_alter_table("duel_offers") as batch:
        batch.alter_column("user_id", nullable=True)
        batch.alter_column("wallet_id", nullable=True)
    with op.batch_alter_table("duel_players") as batch:
        batch.alter_column("user_id", nullable=True)
        batch.alter_column("wallet_id", nullable=True)
    # Older workers intentionally skipped permissionless operations. Replaying
    # both independent contracts is safe because chain events are idempotent.
    op.execute("DELETE FROM chain_checkpoints")


def downgrade() -> None:
    # External projections may contain null identities, so a downgrade cannot
    # preserve them. Production rollback restores the pre-migration backup.
    raise RuntimeError("20260721_0005 is intentionally irreversible")
