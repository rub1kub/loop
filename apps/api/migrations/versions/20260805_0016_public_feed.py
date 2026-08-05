"""Allow blockchain-confirmed public activity cards in the notification outbox."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260805_0016"
down_revision: str | None = "20260802_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("notification_kind", "notification_outbox", type_="check")
    op.create_check_constraint(
        "notification_kind",
        "notification_outbox",
        "kind IN ('result', 'duel_matched', 'referral_qualified', "
        "'duel_reveal_soon', 'public_feed')",
    )


def downgrade() -> None:
    op.drop_constraint("notification_kind", "notification_outbox", type_="check")
    op.create_check_constraint(
        "notification_kind",
        "notification_outbox",
        "kind IN ('result', 'duel_matched', 'referral_qualified', 'duel_reveal_soon')",
    )
