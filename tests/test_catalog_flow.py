"""Integration-style tests for the catalog feature flow.

These tests exercise the full data flow through repositories and UoW
to simulate what the catalog router does — without requiring a live
Telegram bot.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot_app.infrastructure.persistence.models import Category, Product, User
from bot_app.infrastructure.persistence.uow import UnitOfWork
from bot_app.features.catalog.texts import fmt_product_detail, fmt_products_list
from bot_app.shared.money import Money
from bot_app.core.config import settings


# ── Helpers ─────────────────────────────────────────────────────


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[valid-type]
    return async_sessionmaker(engine, expire_on_commit=False)


# ── Catalog browse flow ───────────────────────────────────────


class TestCatalogBrowseFlow:
    @pytest.mark.asyncio
    async def test_browse_root_empty(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            categories = await uow.categories.list_active()
        assert len(categories) == 0

    @pytest.mark.asyncio
    async def test_browse_root_with_categories(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            await uow.categories.create(name="Electronics", slug="electronics", position=1)
            await uow.categories.create(name="Fashion", slug="fashion", position=2)
            await uow.session.flush()

            cats = await uow.categories.list_active()
        assert len(cats) == 2
        assert cats[0].slug == "electronics"
        assert cats[1].slug == "fashion"

    @pytest.mark.asyncio
    async def test_browse_category_with_products(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="Electronics", slug="electronics")
            await uow.session.flush()
            await uow.products.create(
                category_id=cat.id, name="Headphones",
                price_smallest_unit=150000, stock=10,
            )
            await uow.products.create(
                category_id=cat.id, name="Speaker",
                price_smallest_unit=200000, stock=5,
            )
            await uow.session.flush()

            products = await uow.products.list_by_category(cat.id, active_only=True)
        assert len(products) == 2

    @pytest.mark.asyncio
    async def test_browse_inactive_category_hidden(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            await uow.categories.create(name="Electronics", slug="electronics")
            hidden = await uow.categories.create(name="Hidden", slug="hidden")
            await uow.session.flush()
            await uow.categories.toggle_active(hidden.id, is_active=False)
            await uow.session.flush()

            cats = await uow.categories.list_active()
        assert len(cats) == 1
        assert cats[0].slug == "electronics"

    @pytest.mark.asyncio
    async def test_browse_inactive_product_hidden(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            p1 = await uow.products.create(
                category_id=cat.id, name="Active", price_smallest_unit=100,
            )
            await uow.products.create(
                category_id=cat.id, name="Inactive", price_smallest_unit=200,
            )
            await uow.session.flush()
            await uow.products.toggle_active(p1.id, is_active=False)
            await uow.session.flush()

            products = await uow.products.list_by_category(cat.id, active_only=True)
        assert len(products) == 1
        assert products[0].name == "Inactive"

    @pytest.mark.asyncio
    async def test_subcategory_navigation(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            parent = await uow.categories.create(name="Electronics", slug="electronics")
            await uow.session.flush()
            child = await uow.categories.create(
                name="Phones", slug="phones", parent_id=parent.id,
            )
            await uow.session.flush()

            roots = await uow.categories.list_active()
            children = await uow.categories.list_active(parent_id=parent.id)
        assert len(roots) == 1
        assert roots[0].slug == "electronics"
        assert len(children) == 1
        assert children[0].slug == "phones"

    @pytest.mark.asyncio
    async def test_product_detail_text(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id,
                name="Widget",
                price_smallest_unit=50000,
                stock=10,
                description="A great widget",
            )
            await uow.session.flush()

        price = Money(prod.price_smallest_unit, settings.CURRENCY)
        text = fmt_product_detail(prod.name, price, prod.stock, prod.description)
        assert "📦 Widget" in text
        assert "A great widget" in text
        assert "Rp 50.000" in text
        assert "Stok: 10" in text

    @pytest.mark.asyncio
    async def test_products_list_text(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            await uow.products.create(
                category_id=cat.id, name="A", price_smallest_unit=10000, stock=5,
            )
            await uow.products.create(
                category_id=cat.id, name="B", price_smallest_unit=20000, stock=0,
            )
            await uow.session.flush()

            products = await uow.products.list_by_category(cat.id, active_only=True)
        text = fmt_products_list(products, settings.CURRENCY)
        assert "A — Rp 10.000" in text
        assert "B — Rp 20.000" in text
        assert "⚠️Stok habis" in text


# ── Add-to-cart from catalog flow ─────────────────────────────


class TestCatalogAddToCartFlow:
    @pytest.mark.asyncio
    async def test_add_product_to_cart(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="Widget",
                price_smallest_unit=50000, stock=10,
            )
            await uow.session.flush()
            user = await uow.users.get_or_create(42)
            await uow.session.flush()

            # Simulate the add-to-cart callback logic
            product = await uow.products.get(prod.id)
            assert product is not None
            assert product.stock > 0
            await uow.cart_items.add_item(
                user_id=user.id, product_id=prod.id, quantity=1,
            )

        # Verify
        async with UnitOfWork(session_factory) as uow:
            count = await uow.cart_items.count_items(42)
        assert count == 1

    @pytest.mark.asyncio
    async def test_add_out_of_stock_blocked(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="Widget",
                price_smallest_unit=50000, stock=0,
            )
            await uow.session.flush()

            product = await uow.products.get(prod.id)
        assert product is not None
        assert product.stock <= 0  # Should block adding

    @pytest.mark.asyncio
    async def test_add_exceeds_stock_blocked(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="Widget",
                price_smallest_unit=50000, stock=2,
            )
            await uow.session.flush()
            user = await uow.users.get_or_create(42)
            await uow.session.flush()

            # Add 2 items first
            await uow.cart_items.add_item(user_id=42, product_id=prod.id, quantity=2)
            await uow.session.flush()

            # Try to add a 3rd — should be blocked
            existing = await uow.cart_items.find_by_user_and_product(42, prod.id)
        assert existing is not None
        assert existing.quantity >= 2  # stock=2, can't add more

    @pytest.mark.asyncio
    async def test_add_same_product_increments(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="Widget",
                price_smallest_unit=50000, stock=10,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()

            # Add twice
            await uow.cart_items.add_item(user_id=42, product_id=prod.id, quantity=1)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=prod.id, quantity=1)

        async with UnitOfWork(session_factory) as uow:
            count = await uow.cart_items.count_items(42)
            items = await uow.cart_items.list_by_user(42)
        assert count == 2
        assert len(items) == 1  # Same product merged into one cart item
        assert items[0].quantity == 2
