"""Archive social cycles and create independent BANK and DUEL domains."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0004"
down_revision: str | None = "20260721_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for old, archived in [
        ("bank_positions", "legacy_bank_positions"),
        ("bank_cycles", "legacy_bank_cycles"),
        ("cycle_events", "legacy_cycle_events"),
        ("matchmaking_offers", "legacy_matchmaking_offers"),
        ("duels", "legacy_duels"),
        ("inline_invites", "legacy_inline_invites"),
        ("duel_challenges", "legacy_duel_challenges"),
        ("chain_events", "legacy_chain_events"),
    ]:
        op.rename_table(old, archived)

    op.add_column(
        "users",
        sa.Column("onboarding_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "chain_checkpoints",
        sa.Column(
            "heartbeat_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_active_wallet_user",
        "wallets",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("active = true"),
    )

    op.create_table(
        "referral_attributions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("inviter_user_id", sa.String(36), nullable=False),
        sa.Column("invitee_user_id", sa.String(36), nullable=False),
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), server_default="pending", nullable=False),
        sa.Column("qualified_tx_hash", sa.String(96)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("qualified_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["inviter_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["invitee_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["code"], ["referral_codes.code"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invitee_user_id", name="referral_invitee_once"),
        sa.UniqueConstraint("inviter_user_id", "invitee_user_id", name="referral_edge_once"),
    )
    op.create_index(
        "ix_referral_attributions_inviter_user_id", "referral_attributions", ["inviter_user_id"]
    )
    op.create_index(
        "ix_referral_attributions_invitee_user_id", "referral_attributions", ["invitee_user_id"]
    )
    op.create_table(
        "referral_rewards",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("attribution_id", sa.String(36), nullable=False),
        sa.Column("cause", sa.String(64), nullable=False),
        sa.Column("reward_points", sa.Integer(), server_default="0", nullable=False),
        sa.Column("payout_tx_hash", sa.String(96)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["attribution_id"], ["referral_attributions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attribution_id", "cause", name="referral_reward_cause"),
        sa.UniqueConstraint("payout_tx_hash"),
    )
    op.create_index("ix_referral_rewards_attribution_id", "referral_rewards", ["attribution_id"])

    op.create_table(
        "bank_positions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("position_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("wallet_id", sa.String(36), nullable=False),
        sa.Column("owner_wallet", sa.String(68), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("contract_address", sa.String(68), nullable=False),
        sa.Column("query_id", sa.BigInteger(), nullable=False),
        sa.Column("principal_nano", sa.BigInteger(), nullable=False),
        sa.Column("multiplier_bps", sa.Integer(), nullable=False),
        sa.Column("target_payout_nano", sa.BigInteger(), nullable=False),
        sa.Column("funded_amount_nano", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("remaining_amount_nano", sa.BigInteger(), nullable=False),
        sa.Column("queue_index", sa.BigInteger()),
        sa.Column(
            "current_status", sa.String(32), server_default="pending_confirmation", nullable=False
        ),
        sa.Column("funding_transaction", sa.String(96)),
        sa.Column("payout_transaction", sa.String(96)),
        sa.Column("failure_reason", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "network", "contract_address", "position_id", name="bank_position_chain_id"
        ),
        sa.UniqueConstraint(
            "network", "contract_address", "query_id", name="bank_position_query_id"
        ),
    )
    op.create_index("ix_bank_positions_user_id", "bank_positions", ["user_id"])
    op.create_index("ix_bank_positions_wallet_id", "bank_positions", ["wallet_id"])
    op.create_index("ix_bank_positions_current_status", "bank_positions", ["current_status"])
    op.create_index(
        "uq_active_bank_position_wallet",
        "bank_positions",
        ["wallet_id"],
        unique=True,
        postgresql_where=sa.text(
            "current_status IN ('pending_confirmation', 'queued', 'partially_funded', 'completed')"
        ),
    )
    op.create_table(
        "bank_payouts",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("position_id", sa.String(36), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("amount_nano", sa.BigInteger(), nullable=False),
        sa.Column("destination", sa.String(68), nullable=False),
        sa.Column("tx_hash", sa.String(96), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["position_id"], ["bank_positions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("position_id", name="bank_payout_position_once"),
        sa.UniqueConstraint("network", "tx_hash", "position_id", name="bank_payout_chain_id"),
    )
    op.create_index("ix_bank_payouts_position_id", "bank_payouts", ["position_id"])
    op.create_table(
        "bank_chain_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("account", sa.String(68), nullable=False),
        sa.Column("lt", sa.BigInteger(), nullable=False),
        sa.Column("tx_hash", sa.String(96), nullable=False),
        sa.Column("event_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("opcode", sa.BigInteger(), nullable=False),
        sa.Column("position_id", sa.BigInteger()),
        sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("applied", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "network", "account", "lt", "tx_hash", "event_index", name="bank_chain_event_identity"
        ),
    )

    op.create_table(
        "duel_offers",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("onchain_offer_id", sa.BigInteger(), nullable=False),
        sa.Column("query_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("wallet_id", sa.String(36), nullable=False),
        sa.Column("owner_wallet", sa.String(68), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("contract_address", sa.String(68), nullable=False),
        sa.Column("chance_bps", sa.Integer(), nullable=False),
        sa.Column("total_pool_nano", sa.BigInteger(), nullable=False),
        sa.Column("stake_nano", sa.BigInteger(), nullable=False),
        sa.Column("opponent_stake_nano", sa.BigInteger(), nullable=False),
        sa.Column("fee_bps", sa.Integer(), nullable=False),
        sa.Column("payout_nano", sa.BigInteger(), nullable=False),
        sa.Column("commitment_hex", sa.String(64), nullable=False),
        sa.Column("counter_offer_id", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("mode", sa.String(16), server_default="afk", nullable=False),
        sa.Column("state", sa.String(24), server_default="pending_funding", nullable=False),
        sa.Column("revealed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_until", sa.DateTime(timezone=True)),
        sa.Column("funding_tx_hash", sa.String(96)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("network", "onchain_offer_id", name="duel_offer_network_chain_id"),
        sa.UniqueConstraint("network", "query_id", name="duel_offer_query_id"),
    )
    op.create_index("ix_duel_offers_user_id", "duel_offers", ["user_id"])
    op.create_index("ix_duel_offers_wallet_id", "duel_offers", ["wallet_id"])
    op.create_index("ix_duel_offers_state", "duel_offers", ["state"])
    op.create_index("ix_duel_offers_reserved_until", "duel_offers", ["reserved_until"])
    op.create_index(
        "uq_active_duel_offer_wallet",
        "duel_offers",
        ["wallet_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('pending_funding', 'open', 'reserved', 'matched')"),
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
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["offer_a_id"], ["duel_offers.id"]),
        sa.ForeignKeyConstraint(["offer_b_id"], ["duel_offers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("network", "onchain_duel_id", name="duel_chain_id"),
    )
    op.create_index("ix_loop_duels_state", "duels", ["state"])
    op.create_table(
        "duel_players",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("duel_id", sa.String(36), nullable=False),
        sa.Column("offer_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("wallet_id", sa.String(36), nullable=False),
        sa.Column("chance_bps", sa.Integer(), nullable=False),
        sa.Column("stake_nano", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["duel_id"], ["duels.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["duel_offers.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_id"),
        sa.UniqueConstraint("duel_id", "wallet_id", name="duel_player_wallet"),
    )
    op.create_index("ix_duel_players_duel_id", "duel_players", ["duel_id"])
    op.create_index("ix_duel_players_user_id", "duel_players", ["user_id"])
    op.create_table(
        "duel_commits",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("offer_id", sa.String(36), nullable=False),
        sa.Column("commitment_hex", sa.String(64), nullable=False),
        sa.Column("tx_hash", sa.String(96), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["offer_id"], ["duel_offers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("offer_id"),
        sa.UniqueConstraint("tx_hash"),
    )
    op.create_table(
        "duel_reveals",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("duel_id", sa.String(36), nullable=False),
        sa.Column("offer_id", sa.String(36), nullable=False),
        sa.Column("tx_hash", sa.String(96), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["duel_id"], ["duels.id"]),
        sa.ForeignKeyConstraint(["offer_id"], ["duel_offers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tx_hash"),
    )
    op.create_index("ix_duel_reveals_duel_id", "duel_reveals", ["duel_id"])
    op.create_table(
        "duel_settlements",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("duel_id", sa.String(36), nullable=False),
        sa.Column("winner_wallet", sa.String(68)),
        sa.Column("payout_nano", sa.BigInteger(), nullable=False),
        sa.Column("fee_nano", sa.BigInteger(), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("tx_hash", sa.String(96), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["duel_id"], ["duels.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("duel_id"),
        sa.UniqueConstraint("tx_hash"),
    )
    op.create_table(
        "duel_chain_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("network", sa.Integer(), nullable=False),
        sa.Column("account", sa.String(68), nullable=False),
        sa.Column("lt", sa.BigInteger(), nullable=False),
        sa.Column("tx_hash", sa.String(96), nullable=False),
        sa.Column("event_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("opcode", sa.BigInteger(), nullable=False),
        sa.Column("payload_json", sa.Text(), server_default="{}", nullable=False),
        sa.Column("applied", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "network", "account", "lt", "tx_hash", "event_index", name="duel_chain_event_identity"
        ),
    )
    op.create_table(
        "duel_invitations",
        sa.Column("code", sa.String(24), nullable=False),
        sa.Column("creator_user_id", sa.String(36), nullable=False),
        sa.Column("creator_offer_id", sa.String(36), nullable=False),
        sa.Column("accepted_by_user_id", sa.String(36)),
        sa.Column("state", sa.String(24), server_default="open", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["creator_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["creator_offer_id"], ["duel_offers.id"]),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("code"),
        sa.UniqueConstraint("creator_offer_id", name="duel_invitation_offer"),
    )
    op.create_index("ix_duel_invitations_creator_user_id", "duel_invitations", ["creator_user_id"])
    op.create_index(
        "ix_duel_invitations_accepted_by_user_id", "duel_invitations", ["accepted_by_user_id"]
    )
    op.create_index("ix_duel_invitations_state", "duel_invitations", ["state"])
    op.create_index(
        "ix_duel_invitations_state_expires", "duel_invitations", ["state", "expires_at"]
    )


def downgrade() -> None:
    for table in [
        "duel_invitations",
        "duel_chain_events",
        "duel_settlements",
        "duel_reveals",
        "duel_commits",
        "duel_players",
        "duels",
        "duel_offers",
        "bank_chain_events",
        "bank_payouts",
        "bank_positions",
        "referral_rewards",
        "referral_attributions",
    ]:
        op.drop_table(table)
    op.drop_index("uq_active_wallet_user", table_name="wallets")
    op.drop_column("chain_checkpoints", "heartbeat_at")
    op.drop_column("users", "onboarding_enabled")
    for archived, original in [
        ("legacy_bank_positions", "bank_positions"),
        ("legacy_bank_cycles", "bank_cycles"),
        ("legacy_cycle_events", "cycle_events"),
        ("legacy_matchmaking_offers", "matchmaking_offers"),
        ("legacy_duels", "duels"),
        ("legacy_inline_invites", "inline_invites"),
        ("legacy_duel_challenges", "duel_challenges"),
        ("legacy_chain_events", "chain_events"),
    ]:
        op.rename_table(archived, original)
