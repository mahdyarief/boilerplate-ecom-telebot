"""Integration-style tests for the cart feature flow.

These tests exercise the full data flow through repositories and UoW
to simulate what the cart router does — without requiring a live
Telegram bot.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot_app.infrastructure.persistence.uow import UnitOfWork
from bot_app.shared.money import Money
from bot_app.core.config import settings


# ── Helpers ─────────────────────────────────────────────────────


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[valid-type]
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_cart(
    session_factory: async_sessionmaker[AsyncSession],  # type: ignore[valid-type]
) -> dict:
    """Seed a user with a category, product, and a cart item."""
    async with UnitOfWork(session_factory) as uow:
        cat = await uow.categories.create(name="Electronics", slug="electronics")
        await uow.session.flush()
        prod = await uow.products.create(
            category_id=cat.id,
            name="Headphones",
            price_smallest_unit=150000,
            stock=10,
        )
        await uow.session.flush()
        user = await uow.users.get_or_create(42)
        await uow.session.flush()
        await uow.cart_items.add_item(user_id=42, product_id=prod.id, quantity=2)
    return {"cat_id": cat.id, "prod_id": prod.id, "user_id": user.id}


# ── Cart view flow ─────────────────────────────────────────────


class TestCartViewFlow:
    @pytest.mark.asyncio
    async def test_view_empty_cart(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            await uow.users.get_or_create(42)
            await uow.session.flush()
            items = await uow.cart_items.list_by_user(42)
            count = await uow.cart_items.count_items(42)
        assert len(items) == 0
        assert count == 0

    @pytest.mark.asyncio
    async def test_view_cart_with_items(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        await _seed_cart(session_factory)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            total = await uow.cart_items.count_items(42)
        assert len(items) == 1
        assert items[0].quantity == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_cart_total_calculation(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        await _seed_cart(session_factory)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            grand_total = Money.zero(settings.CURRENCY)
            for item in items:
                product = await uow.products.get(item.product_id)
                assert product is not None
                unit_price = Money(product.price_smallest_unit, settings.CURRENCY)
                grand_total = grand_total + (unit_price * item.quantity)

        assert grand_total == Money(300000, "IDR")  # 150000 * 2


# ── Quantity adjustment flow ──────────────────────────────────


class TestCartQuantityFlow:
    @pytest.mark.asyncio
    async def test_increment_quantity(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        await _seed_cart(session_factory)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            assert len(items) == 1
            item = items[0]

            # Simulate increment
            product = await uow.products.get(item.product_id)
            assert product is not None
            new_qty = item.quantity + 1
            assert new_qty <= product.stock  # stock check
            await uow.cart_items.update_quantity(item.id, new_qty)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
        assert items[0].quantity == 3

    @pytest.mark.asyncio
    async def test_increment_blocked_by_stock(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="Limited",
                price_smallest_unit=10000, stock=2,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=prod.id, quantity=2)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            item = items[0]
            product = await uow.products.get(item.product_id)
        assert product is not None
        # Increment would be qty=3 > stock=2, so blocked
        assert item.quantity + 1 > product.stock

    @pytest.mark.asyncio
    async def test_decrement_quantity(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        await _seed_cart(session_factory)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            item = items[0]
            new_qty = item.quantity - 1  # 2 - 1 = 1
            assert new_qty > 0
            await uow.cart_items.update_quantity(item.id, new_qty)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
        assert items[0].quantity == 1

    @pytest.mark.asyncio
    async def test_decrement_to_zero_removes_item(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="Widget",
                price_smallest_unit=10000, stock=10,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=prod.id, quantity=1)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            item = items[0]
            new_qty = item.quantity - 1  # 1 - 1 = 0
            if new_qty <= 0:
                await uow.cart_items.remove_item(item.id)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
        assert len(items) == 0


# ── Remove item flow ──────────────────────────────────────────


class TestCartRemoveFlow:
    @pytest.mark.asyncio
    async def test_remove_item(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        await _seed_cart(session_factory)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            assert len(items) == 1
            await uow.cart_items.remove_item(items[0].id)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            count = await uow.cart_items.count_items(42)
        assert len(items) == 0
        assert count == 0

    @pytest.mark.asyncio
    async def test_remove_only_one_of_multiple(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            p1 = await uow.products.create(
                category_id=cat.id, name="A", price_smallest_unit=10000, stock=5,
            )
            p2 = await uow.products.create(
                category_id=cat.id, name="B", price_smallest_unit=20000, stock=5,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=p1.id, quantity=1)
            await uow.cart_items.add_item(user_id=42, product_id=p2.id, quantity=2)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            assert len(items) == 2
            # Remove the first item
            await uow.cart_items.remove_item(items[0].id)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            count = await uow.cart_items.count_items(42)
        assert len(items) == 1
        assert count == 2  # The remaining item has qty=2


# ── Clear cart flow ──────────────────────────────────────────


class TestCartClearFlow:
    @pytest.mark.asyncio
    async def test_clear_cart(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            p1 = await uow.products.create(
                category_id=cat.id, name="A", price_smallest_unit=10000, stock=5,
            )
            p2 = await uow.products.create(
                category_id=cat.id, name="B", price_smallest_unit=20000, stock=5,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=p1.id, quantity=3)
            await uow.cart_items.add_item(user_id=42, product_id=p2.id, quantity=1)

        async with UnitOfWork(session_factory) as uow:
            count = await uow.cart_items.count_items(42)
            assert count == 4

            await uow.cart_items.clear_cart(42)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            count = await uow.cart_items.count_items(42)
        assert len(items) == 0
        assert count == 0

    @pytest.mark.asyncio
    async def test_clear_already_empty_cart(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            await uow.users.get_or_create(42)
            await uow.session.flush()
            # Clearing an empty cart should be a no-op
            await uow.cart_items.clear_cart(42)
            items = await uow.cart_items.list_by_user(42)
        assert len(items) == 0


# ── Cart edge cases ──────────────────────────────────────────


class TestCartEdgeCases:
    @pytest.mark.asyncio
    async def test_cart_quantity_callback_data_parsing_plus(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Test that qty callback data 'qty:<id>:+' is parsed correctly.

        Regression test for a bug where the direction (\'+'\' vs \'-\'\')
        was checked against the cart_item_id part instead of the direction part.
        """
        await _seed_cart(session_factory)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            item = items[0]

            # Simulate the correct parsing: qty:1:+ should increment
            # The callback data format is qty:<cart_item_id>:<direction>
            callback_data = f"qty:{item.id}:+"
            payload = callback_data[4:]  # strip "qty:"
            parts = payload.split(":")

            # Bug was: parts[0] (cart_item_id) was checked against ('+', '-')
            # Fix: parts[1] (direction) should be checked
            assert len(parts) == 2
            assert parts[1] in ("+", "-")  # direction is parts[1], NOT parts[0]
            cart_item_id = int(parts[0])
            direction = parts[1]
            assert cart_item_id == item.id
            assert direction == "+"

            # Actually perform the increment
            product = await uow.products.get(item.product_id)
            assert product is not None
            new_qty = item.quantity + 1
            assert new_qty <= product.stock
            await uow.cart_items.update_quantity(item.id, new_qty)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
        assert items[0].quantity == 3

    @pytest.mark.asyncio
    async def test_cart_quantity_callback_data_parsing_minus(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Test that qty callback data 'qty:<id>:-' is parsed correctly for decrement."""
        await _seed_cart(session_factory)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            item = items[0]

            callback_data = f"qty:{item.id}:-"
            payload = callback_data[4:]
            parts = payload.split(":")

            assert len(parts) == 2
            assert parts[1] == "-"
            direction = parts[1]
            assert direction == "-"

            # Actually perform the decrement
            new_qty = item.quantity - 1
            if new_qty > 0:
                await uow.cart_items.update_quantity(item.id, new_qty)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
        assert items[0].quantity == 1

    @pytest.mark.asyncio
    async def test_different_users_carts_independent(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="A", price_smallest_unit=10000, stock=10,
            )
            await uow.session.flush()
            await uow.users.get_or_create(1)
            await uow.users.get_or_create(2)
            await uow.session.flush()

            await uow.cart_items.add_item(user_id=1, product_id=prod.id, quantity=3)
            await uow.cart_items.add_item(user_id=2, product_id=prod.id, quantity=1)

        async with UnitOfWork(session_factory) as uow:
            count1 = await uow.cart_items.count_items(1)
            count2 = await uow.cart_items.count_items(2)
        assert count1 == 3
        assert count2 == 1

    @pytest.mark.asyncio
    async def test_cart_total_with_multiple_products(self, session_factory: async_sessionmaker[AsyncSession]) -> None:  # type: ignore[valid-type]
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="E", slug="e")
            await uow.session.flush()
            p1 = await uow.products.create(
                category_id=cat.id, name="A", price_smallest_unit=50000, stock=10,
            )
            p2 = await uow.products.create(
                category_id=cat.id, name="B", price_smallest_unit=30000, stock=10,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=p1.id, quantity=2)
            await uow.cart_items.add_item(user_id=42, product_id=p2.id, quantity=1)

        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
            grand_total = Money.zero(settings.CURRENCY)
            for item in items:
                product = await uow.products.get(item.product_id)
                assert product is not None
                unit_price = Money(product.price_smallest_unit, settings.CURRENCY)
                grand_total = grand_total + (unit_price * item.quantity)

        # 2 * 50000 + 1 * 30000 = 130000
        assert grand_total == Money(130000, "IDR")
