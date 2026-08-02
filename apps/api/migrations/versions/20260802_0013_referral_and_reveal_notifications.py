"""Let the outbox carry a confirmed referral and a reveal deadline warning."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260802_0013"
down_revision: str | None = "20260727_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Migration 0011 created the check under the naming convention on Postgres and
# under its bare name on SQLite, so both spellings have to be dropped.
DROPPABLE = ("ck_notification_outbox_notification_kind", "notification_kind")
KINDS = "kind IN ('result', 'duel_matched', 'referral_qualified', 'duel_reveal_soon')"


def _drop_kind_check() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    for name in DROPPABLE:
        op.execute(f"ALTER TABLE notification_outbox DROP CONSTRAINT IF EXISTS {name}")


def upgrade() -> None:
    _drop_kind_check()
    with op.batch_alter_table("notification_outbox", recreate="always") as batch:
        if op.get_bind().dialect.name == "sqlite":
            batch.drop_constraint("notification_kind", type_="check")
        batch.create_check_constraint("notification_kind", KINDS)


def downgrade() -> None:
    op.execute(
        "DELETE FROM notification_outbox "
        "WHERE kind IN ('referral_qualified', 'duel_reveal_soon')"
    )
    _drop_kind_check()
    with op.batch_alter_table("notification_outbox", recreate="always") as batch:
        if op.get_bind().dialect.name == "sqlite":
            batch.drop_constraint("notification_kind", type_="check")
        batch.create_check_constraint(
            "notification_kind",
            "kind IN ('result', 'duel_matched')",
        )
