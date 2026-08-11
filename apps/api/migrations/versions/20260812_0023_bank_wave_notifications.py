"""Allow the durable outbox to carry weekly BANK Wave messages."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260812_0023"
down_revision: str | None = "20260810_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WITH_WAVE = (
    "kind IN ('result', 'duel_matched', 'referral_qualified', "
    "'duel_reveal_soon', 'public_feed', 'bank_wave')"
)
BEFORE_WAVE = (
    "kind IN ('result', 'duel_matched', 'referral_qualified', 'duel_reveal_soon', 'public_feed')"
)


def _replace(definition: str) -> None:
    # Test databases are created directly from current metadata.
    if op.get_bind().dialect.name == "sqlite":
        return
    op.drop_constraint("notification_kind", "notification_outbox", type_="check")
    op.create_check_constraint("notification_kind", "notification_outbox", definition)


def upgrade() -> None:
    _replace(WITH_WAVE)


def downgrade() -> None:
    op.execute("DELETE FROM notification_outbox WHERE kind = 'bank_wave'")
    _replace(BEFORE_WAVE)
