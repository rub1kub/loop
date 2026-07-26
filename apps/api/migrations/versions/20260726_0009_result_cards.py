"""Add verified result cards and Telegram notification outbox."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0009"
down_revision: str | None = "20260726_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "result_notifications_enabled",
                sa.Boolean(),
                server_default=sa.true(),
                nullable=False,
            )
        )

    op.create_table(
        "result_cards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("event_key", sa.String(length=180), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("payout_nano", sa.BigInteger(), nullable=False),
        sa.Column("contributed_nano", sa.BigInteger(), nullable=False),
        sa.Column("result_nano", sa.BigInteger(), nullable=False),
        sa.Column("tx_hash", sa.String(length=96), nullable=False),
        sa.Column("proof_url", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("share_prepared_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("contributed_nano >= 0", name="ck_result_cards_result_card_contributed"),
        sa.CheckConstraint("mode IN ('bank', 'duel')", name="ck_result_cards_result_card_mode"),
        sa.CheckConstraint("payout_nano >= 0", name="ck_result_cards_result_card_payout"),
        sa.CheckConstraint("result_nano > 0", name="ck_result_cards_result_card_positive"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_result_cards_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_result_cards"),
        sa.UniqueConstraint("event_key", name="result_card_event_once"),
        sa.UniqueConstraint("public_id", name="result_card_public_id"),
    )
    op.create_index(
        "ix_result_cards_user_created",
        "result_cards",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_result_cards_user_id"), "result_cards", ["user_id"], unique=False)

    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("result_card_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(length=64), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('pending', 'processing', 'retry', 'sent', 'blocked', 'failed')",
            name="ck_notification_outbox_notification_state",
        ),
        sa.ForeignKeyConstraint(
            ["result_card_id"],
            ["result_cards.id"],
            name="fk_notification_outbox_result_card_id_result_cards",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_notification_outbox_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notification_outbox"),
        sa.UniqueConstraint("result_card_id", name="notification_result_once"),
    )
    op.create_index(
        "ix_notification_outbox_due",
        "notification_outbox",
        ["state", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_notification_outbox_user_id"),
        "notification_outbox",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_outbox_user_id"), table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_due", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index(op.f("ix_result_cards_user_id"), table_name="result_cards")
    op.drop_index("ix_result_cards_user_created", table_name="result_cards")
    op.drop_table("result_cards")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("result_notifications_enabled")
