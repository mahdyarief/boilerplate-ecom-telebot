"""Integration-style tests for the orders feature.

Tests cover listing orders, viewing detail, and cancellation.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot_app.app.services.checkout import CheckoutService
from bot_app.core.constants import OrderStatus
from bot_app.features.checkout.texts import fmt_order_detail, fmt_orders_list
from bot_app.infrastructure.persistence.uow import UnitOfWork
from bot_app.shared.money import Money
from bot_app.core.config import settings


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[valid-type]
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_order(
    session_factory: async_sessionmaker[AsyncSession],  # type: ignore[valid-type]
    user_id: int = 42,
    status: str = OrderStatus.PAID.value,
) -> int:
    """Create a complete order and return the order_id."""
    async with UnitOfWork(session_factory) as uow:
        cat = await uow.categories.create(name="Test", slug=f"test-ord-{user_id}")
        await uow.session.flush()
        prod = await uow.products.create(
            category_id=cat.id, name="Widget",
            price_smallest_unit=50000, stock=10,
        )
        await uow.session.flush()
        await uow.users.get_or_create(user_id)
        await uow.session.flush()
        await uow.cart_items.add_item(
            user_id=user_id, product_id=prod.id, quantity=2,
        )

    checkout = CheckoutService(session_factory)
    order = await checkout.create_order_from_cart(user_id, "Jl. Test No. 1")

    if status == OrderStatus.PAID.value:
        await checkout.confirm_payment(
            order.id, f"tg_{order.id}", f"pay_{order.id}",
        )
    elif status == OrderStatus.CANCELLED.value:
        await checkout.cancel_order(order.id, user_id)

    return order.id


# ── List orders ──────────────────────────────────────────


class TestOrdersList:
    @pytest.mark.asyncio
    async def test_user_with_no_orders(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with UnitOfWork(session_factory) as uow:
            await uow.users.get_or_create(99)

        async with UnitOfWork(session_factory) as uow:
            orders = await uow.orders.list_by_user(99, limit=10)
        assert len(orders) == 0

    @pytest.mark.asyncio
    async def test_user_with_orders(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        order_id = await _seed_order(session_factory, user_id=42)

        async with UnitOfWork(session_factory) as uow:
            orders = await uow.orders.list_by_user(42, limit=10)
        assert len(orders) >= 1
        assert orders[0].id == order_id


# ── Order detail ─────────────────────────────────────────


class TestOrderDetail:
    @pytest.mark.asyncio
    async def test_order_detail_text(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        order_id = await _seed_order(session_factory, user_id=42)

        async with UnitOfWork(session_factory) as uow:
            order = await uow.orders.get(order_id)
            items = await uow.order_items.list_by_order(order_id)

        text = fmt_order_detail(
            order_id=order.id,
            status=order.status,
            items=items,
            total_smallest_unit=order.total_smallest_unit,
            currency=settings.CURRENCY,
            shipping_address=order.shipping_address,
        )

        assert f"#{order.id}" in text
        assert "Widget" in text
        assert "paid" in text.lower() or "✅" in text
        assert "Jl. Test No. 1" in text

    @pytest.mark.asyncio
    async def test_orders_list_text(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _seed_order(session_factory, user_id=42)

        async with UnitOfWork(session_factory) as uow:
            orders = await uow.orders.list_by_user(42, limit=10)

        text = fmt_orders_list(orders, settings.CURRENCY)
        assert "Pesanan" in text
        assert "paid" in text or "✅" in text

    @pytest.mark.asyncio
    async def test_empty_orders_list_text(self) -> None:
        text = fmt_orders_list([], "IDR")
        assert "belum memiliki" in text


# ── Order cancellation ───────────────────────────────────


class TestOrderCancellation:
    @pytest.mark.asyncio
    async def test_cancel_pending_order(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        order_id = await _seed_order(
            session_factory, user_id=42, status=OrderStatus.PENDING.value,
        )

        checkout = CheckoutService(session_factory)
        cancelled = await checkout.cancel_order(order_id, 42)
        assert cancelled is True

        async with UnitOfWork(session_factory) as uow:
            order = await uow.orders.get(order_id)
        assert order is not None
        assert order.status == OrderStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_paid_order_fails(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        order_id = await _seed_order(
            session_factory, user_id=42, status=OrderStatus.PAID.value,
        )

        checkout = CheckoutService(session_factory)
        cancelled = await checkout.cancel_order(order_id, 42)
        assert cancelled is False

    @pytest.mark.asyncio
    async def test_cancel_other_users_order_fails(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        order_id = await _seed_order(
            session_factory, user_id=42, status=OrderStatus.PENDING.value,
        )

        checkout = CheckoutService(session_factory)
        cancelled = await checkout.cancel_order(order_id, 99)  # different user
        assert cancelled is False

    @pytest.mark.asyncio
    async def test_cancel_releases_stock(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Stock should be incremented back when order is cancelled."""
        # Create product with stock=10 and order 2 items
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="Stock", slug="stock-cancel-test")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="Throwable",
                price_smallest_unit=25000, stock=10,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=prod.id, quantity=2)

        checkout = CheckoutService(session_factory)
        order = await checkout.create_order_from_cart(42, "Address")

        # Stock should be 10 - 2 = 8
        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(prod.id)
        assert product is not None
        assert product.stock == 8

        # Cancel order
        await checkout.cancel_order(order.id, 42)

        # Stock should be back to 10
        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(prod.id)
        assert product is not None
        assert product.stock == 10


# ── Multiple orders ──────────────────────────────────────


class TestMultipleOrders:
    @pytest.mark.asyncio
    async def test_user_can_have_multiple_orders(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        checkout = CheckoutService(session_factory)

        # Create first order
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="Multi", slug="multi-ord-test")
            await uow.session.flush()
            p1 = await uow.products.create(
                category_id=cat.id, name="A",
                price_smallest_unit=10000, stock=20,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()

        # Order 1
        async with UnitOfWork(session_factory) as uow:
            await uow.cart_items.add_item(user_id=42, product_id=p1.id, quantity=3)
        order1 = await checkout.create_order_from_cart(42, "Addr 1")

        # Order 2
        async with UnitOfWork(session_factory) as uow:
            await uow.cart_items.add_item(user_id=42, product_id=p1.id, quantity=2)
        order2 = await checkout.create_order_from_cart(42, "Addr 2")

        async with UnitOfWork(session_factory) as uow:
            orders = await uow.orders.list_by_user(42, limit=10)
        assert len(orders) == 2
        assert order1.id != order2.id
