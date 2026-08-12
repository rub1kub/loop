"""Allow one daily BANK momentum notification per user."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260812_0024"
down_revision: str | None = "20260812_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WITH_MOMENTUM = (
    "kind IN ('result', 'duel_matched', 'referral_qualified', "
    "'duel_reveal_soon', 'public_feed', 'bank_wave', 'bank_momentum')"
)
BEFORE_MOMENTUM = (
    "kind IN ('result', 'duel_matched', 'referral_qualified', "
    "'duel_reveal_soon', 'public_feed', 'bank_wave')"
)


def _replace(definition: str) -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.drop_constraint("notification_kind", "notification_outbox", type_="check")
    op.create_check_constraint("notification_kind", "notification_outbox", definition)


def upgrade() -> None:
    _replace(WITH_MOMENTUM)


def downgrade() -> None:
    op.execute("DELETE FROM notification_outbox WHERE kind = 'bank_momentum'")
    _replace(BEFORE_MOMENTUM)
