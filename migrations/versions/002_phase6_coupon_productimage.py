"""Phase 6 — Add Coupon and ProductImage tables.

Revision ID: 002_phase6_coupon_productimage
Revises: 001_initial_schema
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "002_phase6_coupon_productimage"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Coupon table ────────────────────────────────────────
    op.create_table(
        "coupons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("discount_percent", sa.Integer(), nullable=False, comment="Discount percentage 0-100"),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_coupons_code"),
    )
    op.create_index("ix_coupons_code_active", "coupons", ["code", "is_active"])

    # ── ProductImage table ──────────────────────────────────
    op.create_table(
        "product_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.String(512), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_cover", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_images_product_position", "product_images", ["product_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_product_images_product_position", table_name="product_images")
    op.drop_table("product_images")

    op.drop_index("ix_coupons_code_active", table_name="coupons")
    op.drop_table("coupons")
