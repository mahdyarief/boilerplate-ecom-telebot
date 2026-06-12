"""Tests for SQLAlchemy domain models — relationships, repr, constraints."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot_app.infrastructure.persistence.models import (
    CartItem,
    Category,
    Order,
    Product,
    User,
)


class TestUserModel:
    @pytest.mark.asyncio
    async def test_repr(self, session: AsyncSession) -> None:
        user = User(id=42, language="en", is_admin=True)
        assert "id=42" in repr(user)
        assert "admin=True" in repr(user)


class TestCategoryModel:
    @pytest.mark.asyncio
    async def test_self_referential_relationship(self, session: AsyncSession) -> None:
        parent = Category(name="Electronics", slug="electronics")
        session.add(parent)
        await session.flush()

        child = Category(name="Phones", slug="phones", parent_id=parent.id)
        session.add(child)
        await session.flush()

        result = await session.execute(
            select(Category).where(Category.id == child.id)
        )
        found = result.scalar_one()
        assert found.parent_id == parent.id


class TestProductModel:
    @pytest.mark.asyncio
    async def test_repr(self, session: AsyncSession) -> None:
        product = Product(
            id=1, category_id=1, name="Widget",
            price_smallest_unit=50000, stock=10,
        )
        r = repr(product)
        assert "Widget" in r
        assert "50000" in r


class TestOrderModel:
    @pytest.mark.asyncio
    async def test_default_status_is_pending(self, session: AsyncSession) -> None:
        order = Order(id=1, user_id=42)
        session.add(order)
        await session.flush()
        # Refresh to pick up server/column default
        await session.refresh(order)
        assert order.status == "pending"

    @pytest.mark.asyncio
    async def test_repr(self, session: AsyncSession) -> None:
        order = Order(id=1, user_id=42, status="pending")
        r = repr(order)
        assert "pending" in r


class TestCartItemUniqueConstraint:
    @pytest.mark.asyncio
    async def test_unique_user_product(self, session: AsyncSession) -> None:
        """Inserting two cart items for the same user+product should fail."""
        user = User(id=42)
        cat = Category(name="F", slug="f")
        session.add_all([user, cat])
        await session.flush()

        prod = Product(
            category_id=cat.id, name="P", price_smallest_unit=100,
        )
        session.add(prod)
        await session.flush()

        item1 = CartItem(user_id=42, product_id=prod.id, quantity=1)
        session.add(item1)
        await session.flush()

        item2 = CartItem(user_id=42, product_id=prod.id, quantity=2)
        session.add(item2)

        with pytest.raises(Exception):  # noqa: B017 — IntegrityError is driver-dependent
            # Should raise IntegrityError due to unique constraint
            await session.flush()
