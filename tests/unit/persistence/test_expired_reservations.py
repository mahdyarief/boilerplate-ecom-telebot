"""Tests for expired order reservation reaper."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot_app.app.services.checkout import CheckoutService
from bot_app.core.constants import OrderStatus
from bot_app.infrastructure.persistence.uow import UnitOfWork


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[valid-type]
    return async_sessionmaker(engine, expire_on_commit=False)


# ── list_pending_expired ────────────────────────────────────


class TestListPendingExpired:
    @pytest.mark.asyncio
    async def test_no_expired_orders(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """When no orders exist, the list should be empty."""
        async with UnitOfWork(session_factory) as uow:
            expired = await uow.orders.list_pending_expired(ttl_minutes=15)
        assert len(expired) == 0

    @pytest.mark.asyncio
    async def test_recent_orders_not_expired(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Orders created within TTL should not show as expired."""
        async with UnitOfWork(session_factory) as uow:
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.orders.create(user_id=42)
            await uow.session.flush()
            expired = await uow.orders.list_pending_expired(ttl_minutes=15)
        assert len(expired) == 0

    @pytest.mark.asyncio
    async def test_paid_orders_not_expired(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Paid orders should never show as expired regardless of age."""
        async with UnitOfWork(session_factory) as uow:
            await uow.users.get_or_create(42)
            await uow.session.flush()
            order = await uow.orders.create(user_id=42)
            await uow.session.flush()
            await uow.orders.update_status(order.id, OrderStatus.PAID)
            expired = await uow.orders.list_pending_expired(ttl_minutes=0)
        assert len(expired) == 0

    @pytest.mark.asyncio
    async def test_cancelled_orders_not_expired(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Cancelled orders should not show as expired."""
        async with UnitOfWork(session_factory) as uow:
            await uow.users.get_or_create(42)
            await uow.session.flush()
            order = await uow.orders.create(user_id=42)
            await uow.session.flush()
            await uow.orders.update_status(order.id, OrderStatus.CANCELLED)
            # Very short TTL — would normally expire
            expired = await uow.orders.list_pending_expired(ttl_minutes=0)
        assert len(expired) == 0


# ── release_expired_reservations (service) ────────────────


class TestReleaseExpiredReservations:
    @pytest.mark.asyncio
    async def test_no_expired_orders(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        checkout = CheckoutService(session_factory)
        count = await checkout.release_expired_reservations()
        assert count == 0

    @pytest.mark.asyncio
    async def test_release_expired_order_stock(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """An expired pending order should have its stock released."""
        # Create product with stock=10 and order 3 items
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="Exp", slug="exp-test")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="Expirable",
                price_smallest_unit=25000, stock=10,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=prod.id, quantity=3)

        checkout = CheckoutService(session_factory)
        order = await checkout.create_order_from_cart(42, "Addr")

        # Verify stock was decremented
        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(prod.id)
        assert product is not None
        assert product.stock == 7  # 10 - 3

        # Release expired reservations (TTL=0 means everything is expired)
        import bot_app.core.config as config
        original_ttl = config.settings.ORDER_RESERVATION_TTL
        try:
            # Temporarily set TTL to 0 to force expiration
            config.settings.ORDER_RESERVATION_TTL = 0
            count = await checkout.release_expired_reservations()
        finally:
            config.settings.ORDER_RESERVATION_TTL = original_ttl

        assert count == 1

        # Verify stock was restored and order cancelled
        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(prod.id)
            updated = await uow.orders.get(order.id)
        assert product is not None
        assert product.stock == 10  # restored
        assert updated is not None
        assert updated.status == OrderStatus.CANCELLED.value
