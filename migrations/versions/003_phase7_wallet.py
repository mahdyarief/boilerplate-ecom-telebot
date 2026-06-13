"""Phase 7 — Add Wallet and WalletTransaction tables.

Revision ID: 003_phase7_wallet
Revises: 002_phase6_coupon_productimage
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "003_phase7_wallet"
down_revision = "002_phase6_coupon_productimage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Wallet table ─────────────────────────────────────────
    op.create_table(
        "wallets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "balance_smallest_unit",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Current wallet balance in smallest currency unit",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_wallets_user_id"),
    )

    # ── WalletTransaction table ──────────────────────────────
    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("wallet_id", sa.Integer(), nullable=False),
        sa.Column(
            "transaction_type",
            sa.String(32),
            nullable=False,
            comment="top_up | payment | refund | admin_adjust",
        ),
        sa.Column(
            "amount_smallest_unit",
            sa.Integer(),
            nullable=False,
            comment="Positive for credit, negative for debit",
        ),
        sa.Column(
            "balance_after",
            sa.Integer(),
            nullable=False,
            comment="Wallet balance after this transaction",
        ),
        sa.Column(
            "order_id",
            sa.Integer(),
            nullable=True,
            comment="Related order (for payment/refund)",
        ),
        sa.Column(
            "note",
            sa.String(512),
            nullable=True,
            comment="Human-readable note for the transaction",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["wallet_id"], ["wallets.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_wallet_tx_wallet_type",
        "wallet_transactions",
        ["wallet_id", "transaction_type"],
    )
    op.create_index(
        "ix_wallet_tx_order",
        "wallet_transactions",
        ["order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_wallet_tx_order", table_name="wallet_transactions")
    op.drop_index("ix_wallet_tx_wallet_type", table_name="wallet_transactions")
    op.drop_table("wallet_transactions")
    op.drop_table("wallets")
