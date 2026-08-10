"""Add owner-managed team avatars."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0022"
down_revision: str | None = "20260810_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("avatar_jpeg", sa.LargeBinary(), nullable=True))
    op.add_column("teams", sa.Column("avatar_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("teams", "avatar_sha256")
    op.drop_column("teams", "avatar_jpeg")
