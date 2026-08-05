"""Allow blockchain-confirmed public activity cards in the notification outbox."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260805_0016"
down_revision: str | None = "20260802_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


KINDS_WITH_FEED = (
    "kind IN ('result', 'duel_matched', 'referral_qualified', 'duel_reveal_soon', 'public_feed')"
)
KINDS_BEFORE_FEED = "kind IN ('result', 'duel_matched', 'referral_qualified', 'duel_reveal_soon')"


def _replace_kind_check(new_definition: str) -> None:
    # SQLite cannot ALTER a constraint, and the integration suite runs on it.
    # Recreating the table there would buy nothing: the suite starts from an
    # empty database, so the table is created with the current definition.
    if op.get_bind().dialect.name == "sqlite":
        return
    op.drop_constraint("notification_kind", "notification_outbox", type_="check")
    op.create_check_constraint("notification_kind", "notification_outbox", new_definition)


def upgrade() -> None:
    _replace_kind_check(KINDS_WITH_FEED)


def downgrade() -> None:
    _replace_kind_check(KINDS_BEFORE_FEED)
