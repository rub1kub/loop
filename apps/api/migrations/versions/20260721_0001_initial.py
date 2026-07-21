"""Frozen historical LOOP schema before BANK/DUEL separation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64)),
        sa.Column("first_name", sa.String(128), nullable=False),
        sa.Column("last_name", sa.String(128)),
        sa.Column("language_code", sa.String(16)),
        sa.Column("photo_url", sa.Text()),
        sa.Column("referred_by_id", sa.String(36)),
        sa.Column("onboarding_seen", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["referred_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_table(
        "auth_exchanges",
        sa.Column("digest", sa.LargeBinary(32), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("auth_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("digest"),
    )
    op.create_table(
        "wallets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("address", sa.String(68), nullable=False),
        sa.Column("public_key", sa.String(64), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("network", "address", name="wallet_network_address"),
    )
    op.create_index("ix_wallets_user_id", "wallets", ["user_id"])
    op.create_table(
        "bank_positions",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("target_nano", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "referral_codes",
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("owner_user_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("code"),
        sa.UniqueConstraint("owner_user_id"),
    )
    op.create_table(
        "matchmaking_offers",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("onchain_offer_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("wallet_id", sa.String(36), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("contract_address", sa.String(68), nullable=False),
        sa.Column("chance_bps", sa.Integer(), nullable=False),
        sa.Column("total_pool_nano", sa.BigInteger(), nullable=False),
        sa.Column("stake_nano", sa.BigInteger(), nullable=False),
        sa.Column("commitment_hex", sa.String(64), nullable=False),
        sa.Column("counter_offer_id", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("state", sa.String(24), server_default="pending_funding", nullable=False),
        sa.Column("revealed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("funding_tx_hash", sa.String(96)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("network", "onchain_offer_id", name="offer_network_chain_id"),
    )
    op.create_index("ix_matchmaking_offers_user_id", "matchmaking_offers", ["user_id"])
    op.create_index("ix_matchmaking_offers_state", "matchmaking_offers", ["state"])
    op.create_index(
        "uq_active_offer_wallet",
        "matchmaking_offers",
        ["wallet_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('pending_funding', 'open', 'matched')"),
    )
    op.create_table(
        "duels",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("onchain_duel_id", sa.BigInteger(), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("offer_a_id", sa.String(36), nullable=False),
        sa.Column("offer_b_id", sa.String(36), nullable=False),
        sa.Column("state", sa.String(24), server_default="revealing", nullable=False),
        sa.Column("winner_wallet", sa.String(68)),
        sa.Column("reveal_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_tx_hash", sa.String(96)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["offer_a_id"], ["matchmaking_offers.id"]),
        sa.ForeignKeyConstraint(["offer_b_id"], ["matchmaking_offers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("network", "onchain_duel_id", name="duel_chain_id"),
    )
    op.create_index("ix_duels_state", "duels", ["state"])
    op.create_table(
        "inline_invites",
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("creator_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("stake_nano", sa.BigInteger(), nullable=False),
        sa.Column("chance_bps", sa.Integer(), nullable=False),
        sa.Column("accepted_by_user_id", sa.String(36)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_table(
        "chain_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("account", sa.String(68), nullable=False),
        sa.Column("lt", sa.BigInteger(), nullable=False),
        sa.Column("tx_hash", sa.String(96), nullable=False),
        sa.Column("opcode", sa.BigInteger()),
        sa.Column("body_hash", sa.String(96)),
        sa.Column("applied", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("network", "account", "lt", "tx_hash", name="chain_event_identity"),
    )
    op.create_table(
        "chain_checkpoints",
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("last_lt", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    for table in [
        "chain_checkpoints",
        "chain_events",
        "inline_invites",
        "duels",
        "matchmaking_offers",
        "referral_codes",
        "bank_positions",
        "wallets",
        "auth_exchanges",
        "users",
    ]:
        op.drop_table(table)
