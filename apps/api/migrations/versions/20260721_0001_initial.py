"""Initial LOOP schema."""

from collections.abc import Sequence

from alembic import op

from app.database import Base

revision: str = "20260721_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    initial_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name not in {"bank_cycles", "cycle_events", "duel_challenges"}
    ]
    Base.metadata.create_all(bind=bind, tables=initial_tables)


def downgrade() -> None:
    bind = op.get_bind()
    initial_tables = [
        table
        for name, table in Base.metadata.tables.items()
        if name not in {"bank_cycles", "cycle_events", "duel_challenges"}
    ]
    Base.metadata.drop_all(bind=bind, tables=initial_tables)
