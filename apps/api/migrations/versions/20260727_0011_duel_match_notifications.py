"""Carry non-result notifications in the outbox so a matched duel can warn its players."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_0011"
down_revision: str | None = "20260726_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("notification_outbox") as batch:
        batch.add_column(
            sa.Column(
                "kind",
                sa.String(length=24),
                server_default="result",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "payload_json",
                sa.Text(),
                server_default="{}",
                nullable=False,
            )
        )
        batch.add_column(sa.Column("dedupe_key", sa.String(length=180), nullable=True))
        batch.alter_column(
            "result_card_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )

    op.execute(
        "UPDATE notification_outbox SET dedupe_key = 'result:' || result_card_id "
        "WHERE dedupe_key IS NULL"
    )

    with op.batch_alter_table("notification_outbox") as batch:
        batch.alter_column(
            "dedupe_key",
            existing_type=sa.String(length=180),
            nullable=False,
        )
        batch.drop_constraint("notification_result_once", type_="unique")
        batch.create_unique_constraint("notification_dedupe_once", ["dedupe_key"])
        batch.create_check_constraint(
            "notification_kind",
            "kind IN ('result', 'duel_matched')",
        )


def downgrade() -> None:
    op.execute("DELETE FROM notification_outbox WHERE kind <> 'result'")
    if op.get_bind().dialect.name != "sqlite":
        op.execute(
            "ALTER TABLE notification_outbox "
            "DROP CONSTRAINT IF EXISTS ck_notification_outbox_notification_kind"
        )
    with op.batch_alter_table("notification_outbox") as batch:
        if op.get_bind().dialect.name == "sqlite":
            batch.drop_constraint("notification_kind", type_="check")
        batch.drop_constraint("notification_dedupe_once", type_="unique")
        batch.create_unique_constraint("notification_result_once", ["result_card_id"])
        batch.alter_column(
            "result_card_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch.drop_column("dedupe_key")
        batch.drop_column("payload_json")
        batch.drop_column("kind")
