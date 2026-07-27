"""Let a BANK contribution produce its own share card, which reports no result."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0012"
down_revision: str | None = "20260727_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DROPPABLE_MODE = (
    "ck_result_cards_ck_result_cards_result_card_mode",
    "ck_result_cards_result_card_mode",
    "result_card_mode",
)
DROPPABLE_POSITIVE = (
    "ck_result_cards_ck_result_cards_result_card_positive",
    "ck_result_cards_result_card_positive",
    "result_card_positive",
)


def upgrade() -> None:
    with op.batch_alter_table("result_cards") as batch:
        batch.add_column(sa.Column("queue_position", sa.Integer(), nullable=True))
        batch.alter_column(
            "mode",
            existing_type=sa.String(length=8),
            type_=sa.String(length=16),
            existing_nullable=False,
        )

    if op.get_bind().dialect.name != "sqlite":
        for stale in DROPPABLE_MODE + DROPPABLE_POSITIVE:
            op.execute(f"ALTER TABLE result_cards DROP CONSTRAINT IF EXISTS {stale}")
        op.execute(
            "ALTER TABLE result_cards ADD CONSTRAINT ck_result_cards_result_card_mode "
            "CHECK (mode IN ('bank', 'duel', 'bank_entry'))"
        )
        op.execute(
            "ALTER TABLE result_cards ADD CONSTRAINT ck_result_cards_result_card_positive "
            "CHECK ((mode = 'bank_entry' AND result_nano = 0 AND payout_nano = 0)"
            " OR (mode <> 'bank_entry' AND result_nano > 0))"
        )
        return

    with op.batch_alter_table("result_cards", recreate="always") as batch:
        batch.drop_constraint("ck_result_cards_result_card_mode", type_="check")
        batch.drop_constraint("ck_result_cards_result_card_positive", type_="check")
        batch.create_check_constraint(
            "result_card_mode",
            "mode IN ('bank', 'duel', 'bank_entry')",
        )
        batch.create_check_constraint(
            "result_card_positive",
            "(mode = 'bank_entry' AND result_nano = 0 AND payout_nano = 0)"
            " OR (mode <> 'bank_entry' AND result_nano > 0)",
        )


def downgrade() -> None:
    op.execute("DELETE FROM result_cards WHERE mode = 'bank_entry'")

    if op.get_bind().dialect.name != "sqlite":
        for stale in DROPPABLE_MODE + DROPPABLE_POSITIVE:
            op.execute(f"ALTER TABLE result_cards DROP CONSTRAINT IF EXISTS {stale}")
        op.execute(
            "ALTER TABLE result_cards ADD CONSTRAINT ck_result_cards_result_card_mode "
            "CHECK (mode IN ('bank', 'duel'))"
        )
        op.execute(
            "ALTER TABLE result_cards ADD CONSTRAINT ck_result_cards_result_card_positive "
            "CHECK (result_nano > 0)"
        )
    else:
        with op.batch_alter_table("result_cards", recreate="always") as batch:
            batch.drop_constraint("result_card_mode", type_="check")
            batch.drop_constraint("result_card_positive", type_="check")
            batch.create_check_constraint(
                "ck_result_cards_result_card_mode", "mode IN ('bank', 'duel')"
            )
            batch.create_check_constraint(
                "ck_result_cards_result_card_positive", "result_nano > 0"
            )

    with op.batch_alter_table("result_cards") as batch:
        batch.alter_column(
            "mode",
            existing_type=sa.String(length=16),
            type_=sa.String(length=8),
            existing_nullable=False,
        )
        batch.drop_column("queue_position")
