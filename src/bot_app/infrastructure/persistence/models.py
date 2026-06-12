"""SQLAlchemy declarative base and domain models.

These models define the *target* schema for the shop bot.  Alembic owns
all migrations — never call ``Base.metadata.create_all`` in production.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ...core.constants import OrderStatus, PaymentStatus

# ── Base ────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """Declarative base for all domain models."""


# ── Mixins ──────────────────────────────────────────────────────


class _TimestampMixin:
    """Provides ``created_at`` with a server-side default."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


# ── User ────────────────────────────────────────────────────────


class User(Base, _TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    language: Mapped[str] = mapped_column(String(5), default="id")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── relationships ───────────────────────────────────────
    orders: Mapped[list[Order]] = relationship(
        "Order",
        back_populates="user",
        lazy="selectin",
    )
    cart_items: Mapped[list[CartItem]] = relationship(
        "CartItem",
        back_populates="user",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} lang={self.language!r} admin={self.is_admin}>"


# ── Category ────────────────────────────────────────────────────


class Category(Base, _TimestampMixin):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_categories_slug"),
        Index("ix_categories_parent_active", "parent_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True)
    parent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("categories.id"),
        nullable=True,
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── relationships ───────────────────────────────────────
    parent: Mapped[Category | None] = relationship(
        "Category",
        remote_side=[id],
        back_populates="children",
    )
    children: Mapped[list[Category]] = relationship(
        "Category",
        back_populates="parent",
        lazy="selectin",
    )
    products: Mapped[list[Product]] = relationship(
        "Product",
        back_populates="category",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} slug={self.slug!r} active={self.is_active}>"


# ── Product ────────────────────────────────────────────────────


class Product(Base, _TimestampMixin):
    __tablename__ = "products"
    __table_args__ = (Index("ix_products_category_active", "category_id", "is_active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_smallest_unit: Mapped[int] = mapped_column(
        Integer,
        comment="e.g. 50000 for IDR 50.000",
    )
    stock: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── relationships ───────────────────────────────────────
    category: Mapped[Category] = relationship(
        "Category",
        back_populates="products",
    )
    cart_items: Mapped[list[CartItem]] = relationship(
        "CartItem",
        back_populates="product",
        lazy="selectin",
    )
    order_items: Mapped[list[OrderItem]] = relationship(
        "OrderItem",
        back_populates="product",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<Product id={self.id} name={self.name!r} "
            f"price={self.price_smallest_unit} stock={self.stock}>"
        )


# ── CartItem (transient — Redis in prod, SQL fallback) ────────


class CartItem(Base, _TimestampMixin):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),
        Index("ix_cart_items_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    # ── relationships ───────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="cart_items")
    product: Mapped[Product] = relationship("Product", back_populates="cart_items")

    def __repr__(self) -> str:
        return (
            f"<CartItem id={self.id} user={self.user_id} "
            f"product={self.product_id} qty={self.quantity}>"
        )


# ── Order ──────────────────────────────────────────────────────


class Order(Base, _TimestampMixin):
    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default=OrderStatus.PENDING.value,
    )
    total_smallest_unit: Mapped[int] = mapped_column(Integer, default=0)
    shipping_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # ── relationships ───────────────────────────────────────
    user: Mapped[User] = relationship("User", back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(
        "OrderItem",
        back_populates="order",
        lazy="selectin",
    )
    payments: Mapped[list[Payment]] = relationship(
        "Payment",
        back_populates="order",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Order id={self.id} user={self.user_id} status={self.status!r}>"


# ── OrderItem ──────────────────────────────────────────────────


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (Index("ix_order_items_order", "order_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_smallest_unit: Mapped[int] = mapped_column(Integer)

    # ── relationships ───────────────────────────────────────
    order: Mapped[Order] = relationship("Order", back_populates="items")
    product: Mapped[Product] = relationship("Product", back_populates="order_items")

    def __repr__(self) -> str:
        return (
            f"<OrderItem id={self.id} order={self.order_id} "
            f"product={self.product_name!r} qty={self.quantity}>"
        )


# ── Payment ───────────────────────────────────────────────────


class Payment(Base, _TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_order", "order_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"))
    provider: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(32),
        default=PaymentStatus.PENDING.value,
    )
    telegram_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── relationships ───────────────────────────────────────
    order: Mapped[Order] = relationship("Order", back_populates="payments")

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} order={self.order_id} "
            f"provider={self.provider!r} status={self.status!r}>"
        )


# ── Coupon ──────────────────────────────────────────────────


class Coupon(Base, _TimestampMixin):
    __tablename__ = "coupons"
    __table_args__ = (
        UniqueConstraint("code", name="uq_coupons_code"),
        Index("ix_coupons_code_active", "code", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    discount_percent: Mapped[int] = mapped_column(
        Integer,
        comment="Discount percentage 0-100",
    )
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return (
            f"<Coupon id={self.id} code={self.code!r} "
            f"discount={self.discount_percent}% uses={self.used_count}/{self.max_uses}>"
        )


# ── ProductImage ─────────────────────────────────────────────


class ProductImage(Base, _TimestampMixin):
    __tablename__ = "product_images"
    __table_args__ = (
        Index("ix_product_images_product_position", "product_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id"))
    file_id: Mapped[str] = mapped_column(String(512))
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── relationships ───────────────────────────────────────
    product: Mapped[Product] = relationship("Product")

    def __repr__(self) -> str:
        return (
            f"<ProductImage id={self.id} product={self.product_id} "
            f"cover={self.is_cover} pos={self.position}>"
        )
