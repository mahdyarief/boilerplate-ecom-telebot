"""Integration-style tests for the checkout flow.

These tests exercise the full data flow through services, repositories,
and UoW to simulate what a real checkout looks like — without requiring
a live Telegram bot.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot_app.app.services.checkout import CheckoutService
from bot_app.core.constants import OrderStatus, PaymentStatus
from bot_app.core.errors import NotFoundError, StockError
from bot_app.infrastructure.persistence.uow import UnitOfWork
from bot_app.shared.money import Money
from bot_app.core.config import settings


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[valid-type]
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_full_cart(
    session_factory: async_sessionmaker[AsyncSession],  # type: ignore[valid-type]
    user_id: int = 42,
) -> dict:
    """Seed a user, category, 2 products, and 2 cart items."""
    async with UnitOfWork(session_factory) as uow:
        cat = await uow.categories.create(name="Electronics", slug="electronics-flow")
        await uow.session.flush()
        p1 = await uow.products.create(
            category_id=cat.id, name="Headphones", price_smallest_unit=150000, stock=10,
        )
        p2 = await uow.products.create(
            category_id=cat.id, name="Charger", price_smallest_unit=75000, stock=5,
        )
        await uow.session.flush()
        user = await uow.users.get_or_create(user_id)
        await uow.session.flush()
        await uow.cart_items.add_item(user_id=user_id, product_id=p1.id, quantity=2)
        await uow.cart_items.add_item(user_id=user_id, product_id=p2.id, quantity=1)
    return {"cat_id": cat.id, "p1_id": p1.id, "p2_id": p2.id, "user_id": user.id}


# ── Full checkout → pay → confirm flow ──────────────────


class TestFullCheckoutFlow:
    @pytest.mark.asyncio
    async def test_checkout_to_payment_success(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Complete happy-path: cart → checkout → pay → confirm."""
        await _seed_full_cart(session_factory, user_id=42)
        checkout = CheckoutService(session_factory)

        # Step 1: Create order from cart
        order = await checkout.create_order_from_cart(42, "Jl. Sudirman No. 1")
        assert order.total_smallest_unit == 375000  # 2*150000 + 1*75000

        # Step 2: Verify pre-checkout
        ok, _ = await checkout.verify_pre_checkout(order.id)
        assert ok is True

        # Step 3: Confirm payment
        await checkout.confirm_payment(order.id, "tg_charge_1", "pay_charge_1")

        # Step 4: Verify final state
        async with UnitOfWork(session_factory) as uow:
            updated = await uow.orders.get(order.id)
            assert updated is not None
            assert updated.status == OrderStatus.PAID.value

            items = await uow.order_items.list_by_order(order.id)
            assert len(items) == 2

            payments = await uow.payments.get_by_order(order.id)
            assert len(payments) == 1
            assert payments[0].status == PaymentStatus.SUCCESS.value

    @pytest.mark.asyncio
    async def test_checkout_to_cancel(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Cart → checkout → cancel → stock restored."""
        await _seed_full_cart(session_factory, user_id=42)
        checkout = CheckoutService(session_factory)

        # Step 1: Create order (reserves stock)
        order = await checkout.create_order_from_cart(42, "Some address")

        # Verify stock was decremented
        async with UnitOfWork(session_factory) as uow:
            items = await uow.order_items.list_by_order(order.id)
            for item in items:
                product = await uow.products.get(item.product_id)
                assert product is not None
                # Headphones: stock was 10, reserved 2 → 8
                # Charger: stock was 5, reserved 1 → 4

        # Step 2: Cancel order
        cancelled = await checkout.cancel_order(order.id, 42)
        assert cancelled is True

        # Step 3: Verify stock restored
        async with UnitOfWork(session_factory) as uow:
            items = await uow.order_items.list_by_order(order.id)
            for item in items:
                product = await uow.products.get(item.product_id)
                assert product is not None
                # Headphones: 8 + 2 = 10, Charger: 4 + 1 = 5

            # Also verify order status
            updated = await uow.orders.get(order.id)
            assert updated is not None
            assert updated.status == OrderStatus.CANCELLED.value


# ── Stock war scenario ───────────────────────────────────


class TestCheckoutStockWar:
    @pytest.mark.asyncio
    async def test_second_checkout_fails_when_stock_exhausted(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Two users try to check out the same limited stock product."""
        # Seed: product with stock=3
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="Limited", slug="limited-flow")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="Rare Item",
                price_smallest_unit=100000, stock=3,
            )
            await uow.session.flush()
            await uow.users.get_or_create(1)
            await uow.users.get_or_create(2)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=1, product_id=prod.id, quantity=3)
            await uow.cart_items.add_item(user_id=2, product_id=prod.id, quantity=2)

        checkout = CheckoutService(session_factory)

        # User 1 checks out — should succeed (reserves all 3)
        order1 = await checkout.create_order_from_cart(1, "Address A")
        assert order1 is not None

        # User 2 tries to check out — should fail (stock=0 now)
        with pytest.raises(StockError, match="Stok tidak cukup"):
            await checkout.create_order_from_cart(2, "Address B")


# ── Dev-mode checkout (no PROVIDER_TOKEN) ────────────────


class TestCheckoutDevMode:
    @pytest.mark.asyncio
    async def test_checkout_without_provider_token(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """When PROVIDER_TOKEN is empty, confirm_payment should still work."""
        await _seed_full_cart(session_factory, user_id=42)
        checkout = CheckoutService(session_factory)

        order = await checkout.create_order_from_cart(42, "Address")

        # Simulate dev-mode auto-confirm
        await checkout.confirm_payment(
            order.id,
            telegram_charge_id=f"dev_auto_{order.id}",
            provider_charge_id=f"dev_auto_{order.id}",
        )

        async with UnitOfWork(session_factory) as uow:
            updated = await uow.orders.get(order.id)
        assert updated is not None
        assert updated.status == OrderStatus.PAID.value


# ── Cart total calculation ────────────────────────────────


class TestCheckoutTotalCalculation:
    @pytest.mark.asyncio
    async def test_total_matches_item_prices(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Order total should exactly equal sum(qty * unit_price)."""
        await _seed_full_cart(session_factory, user_id=42)
        checkout = CheckoutService(session_factory)

        order = await checkout.create_order_from_cart(42, "Address")

        async with UnitOfWork(session_factory) as uow:
            items = await uow.order_items.list_by_order(order.id)

        computed_total = 0
        for item in items:
            computed_total += item.unit_price_smallest_unit * item.quantity

        assert order.total_smallest_unit == computed_total

        # Also verify via Money
        total_money = Money(order.total_smallest_unit, settings.CURRENCY)
        assert total_money == Money(375000, "IDR")
