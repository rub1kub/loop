"""Add address-bound DUEL v1.1 invitation state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0006"
down_revision: str | None = "20260721_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    active_offers = int(
        connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM duel_offers "
                "WHERE state IN ('pending_funding', 'open', 'reserved', 'matched')"
            )
        ).scalar_one()
    )
    active_duels = int(
        connection.execute(
            sa.text("SELECT COUNT(*) FROM duels WHERE state = 'revealing'")
        ).scalar_one()
    )
    active_invitations = int(
        connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM duel_invitations "
                "WHERE state IN ('accepted', 'funding', 'matched')"
            )
        ).scalar_one()
    )
    if active_offers or active_duels or active_invitations:
        raise RuntimeError(
            "DUEL v1.1 migration requires an idle projection: "
            f"offers={active_offers}, duels={active_duels}, "
            f"invitations={active_invitations}"
        )

    with op.batch_alter_table("duel_offers") as batch:
        batch.add_column(sa.Column("invite_id_hex", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("direct_opponent_wallet", sa.String(length=68), nullable=True))
    with op.batch_alter_table("duel_invitations") as batch:
        batch.add_column(sa.Column("invite_id_hex", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("accepted_wallet_address", sa.String(length=68), nullable=True))

    # V1 invitations did not carry an on-chain address-bound permit. They must
    # never be accepted after the contract switch. The release preflight also
    # requires the V1 contract and active DUEL projection to be empty.
    op.execute(
        "UPDATE duel_invitations SET state = 'expired', "
        "invite_id_hex = '0000000000000000000000000000000000000000000000000000000000000000'"
    )
    with op.batch_alter_table("duel_invitations") as batch:
        batch.alter_column("invite_id_hex", existing_type=sa.String(length=64), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("duel_invitations") as batch:
        batch.drop_column("accepted_wallet_address")
        batch.drop_column("invite_id_hex")
    with op.batch_alter_table("duel_offers") as batch:
        batch.drop_column("direct_opponent_wallet")
        batch.drop_column("invite_id_hex")
