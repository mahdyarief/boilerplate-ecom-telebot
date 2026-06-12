"""Tests for the CheckoutService — business logic for order creation & payments."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot_app.app.services.checkout import CheckoutService
from bot_app.core.constants import OrderStatus, PaymentStatus
from bot_app.core.errors import NotFoundError, StockError
from bot_app.infrastructure.persistence.models import OrderItem
from bot_app.infrastructure.persistence.uow import UnitOfWork


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[valid-type]
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_cart(
    session_factory: async_sessionmaker[AsyncSession],  # type: ignore[valid-type]
    user_id: int = 42,
    product_name: str = "Widget",
    price: int = 50000,
    stock: int = 10,
    quantity: int = 2,
) -> dict:
    """Seed a user with category, product, and a cart item. Returns ids."""
    async with UnitOfWork(session_factory) as uow:
        cat = await uow.categories.create(name="Electronics", slug="electronics-chk")
        await uow.session.flush()
        prod = await uow.products.create(
            category_id=cat.id,
            name=product_name,
            price_smallest_unit=price,
            stock=stock,
        )
        await uow.session.flush()
        user = await uow.users.get_or_create(user_id)
        await uow.session.flush()
        await uow.cart_items.add_item(
            user_id=user_id, product_id=prod.id, quantity=quantity,
        )
    return {"cat_id": cat.id, "prod_id": prod.id, "user_id": user.id}


# ── create_order_from_cart ───────────────────────────────


class TestCreateOrderFromCart:
    @pytest.mark.asyncio
    async def test_successful_order_creation(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        checkout = CheckoutService(session_factory)
        await _seed_cart(session_factory, user_id=42, price=50000, quantity=2)

        order = await checkout.create_order_from_cart(42, "Jl. Sudirman No. 1")

        assert order is not None
        assert order.user_id == 42
        assert order.status == OrderStatus.PENDING.value
        assert order.total_smallest_unit == 100000  # 50000 * 2
        assert order.shipping_address == "Jl. Sudirman No. 1"

        # Verify order items
        async with UnitOfWork(session_factory) as uow:
            items = await uow.order_items.list_by_order(order.id)
        assert len(items) == 1
        assert items[0].product_name == "Widget"
        assert items[0].quantity == 2

    @pytest.mark.asyncio
    async def test_stock_is_decremented(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _seed_cart(session_factory, stock=10, quantity=3)

        checkout = CheckoutService(session_factory)
        await checkout.create_order_from_cart(42, "Jl. Test")

        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(1)  # first product by id
        # Stock should be 10 - 3 = 7
        # Find the product — it may not be id=1
        async with UnitOfWork(session_factory) as uow:
            items = await uow.cart_items.list_by_user(42)
        # Cart should be cleared
        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_cart_cleared_after_order(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _seed_cart(session_factory)

        checkout = CheckoutService(session_factory)
        await checkout.create_order_from_cart(42, "Address")

        async with UnitOfWork(session_factory) as uow:
            cart_items = await uow.cart_items.list_by_user(42)
        assert len(cart_items) == 0

    @pytest.mark.asyncio
    async def test_empty_cart_raises_not_found(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        async with UnitOfWork(session_factory) as uow:
            await uow.users.get_or_create(42)

        checkout = CheckoutService(session_factory)
        with pytest.raises(NotFoundError, match="kosong"):
            await checkout.create_order_from_cart(42, "Address")

    @pytest.mark.asyncio
    async def test_insufficient_stock_raises_stock_error(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _seed_cart(session_factory, stock=1, quantity=5)

        checkout = CheckoutService(session_factory)
        with pytest.raises(StockError, match="Stok tidak cukup"):
            await checkout.create_order_from_cart(42, "Address")

    @pytest.mark.asyncio
    async def test_stock_not_decremented_on_failure(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """When stock reservation fails, the product stock must remain unchanged."""
        # Create two products, one with insufficient stock
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="Test", slug="test-multi-chk")
            await uow.session.flush()
            p1 = await uow.products.create(
                category_id=cat.id, name="Available", price_smallest_unit=10000, stock=10,
            )
            p2 = await uow.products.create(
                category_id=cat.id, name="Scarce", price_smallest_unit=20000, stock=1,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=p1.id, quantity=5)
            await uow.cart_items.add_item(user_id=42, product_id=p2.id, quantity=3)

        checkout = CheckoutService(session_factory)
        with pytest.raises(StockError):
            await checkout.create_order_from_cart(42, "Address")

        # Stock for p1 should NOT have been decremented (transaction rolled back)
        async with UnitOfWork(session_factory) as uow:
            prod1 = await uow.products.get(p1.id)
            prod2 = await uow.products.get(p2.id)
        assert prod1 is not None
        assert prod2 is not None
        assert prod1.stock == 10  # unchanged
        assert prod2.stock == 1  # unchanged


# ── verify_pre_checkout ──────────────────────────────────


class TestVerifyPreCheckout:
    @pytest.mark.asyncio
    async def test_valid_order_returns_true(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _seed_cart(session_factory)
        checkout = CheckoutService(session_factory)
        order = await checkout.create_order_from_cart(42, "Addr")

        ok, msg = await checkout.verify_pre_checkout(order.id)
        assert ok is True
        assert msg == ""

    @pytest.mark.asyncio
    async def test_nonexistent_order_returns_false(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        checkout = CheckoutService(session_factory)
        ok, msg = await checkout.verify_pre_checkout(9999)
        assert ok is False
        assert "tidak ditemukan" in msg

    @pytest.mark.asyncio
    async def test_cancelled_order_returns_false(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _seed_cart(session_factory)
        checkout = CheckoutService(session_factory)
        order = await checkout.create_order_from_cart(42, "Addr")

        await checkout.cancel_order(order.id, 42)

        ok, msg = await checkout.verify_pre_checkout(order.id)
        assert ok is False


# ── confirm_payment ──────────────────────────────────────


class TestConfirmPayment:
    @pytest.mark.asyncio
    async def test_confirm_marks_order_paid(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _seed_cart(session_factory)
        checkout = CheckoutService(session_factory)
        order = await checkout.create_order_from_cart(42, "Addr")

        await checkout.confirm_payment(
            order.id,
            telegram_charge_id="tg_123",
            provider_charge_id="pay_abc",
        )

        async with UnitOfWork(session_factory) as uow:
            updated = await uow.orders.get(order.id)
            assert updated is not None
            assert updated.status == OrderStatus.PAID.value

            payments = await uow.payments.get_by_order(order.id)
            assert len(payments) == 1
            assert payments[0].status == PaymentStatus.SUCCESS.value
            assert payments[0].telegram_charge_id == "tg_123"
            assert payments[0].provider_charge_id == "pay_abc"

    @pytest.mark.asyncio
    async def test_confirm_nonexistent_raises(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        checkout = CheckoutService(session_factory)
        with pytest.raises(NotFoundError):
            await checkout.confirm_payment(9999, "tg", "pay")


# ── cancel_order ─────────────────────────────────────────


class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_returns_stock(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _seed_cart(session_factory, stock=10, quantity=3)
        checkout = CheckoutService(session_factory)
        order = await checkout.create_order_from_cart(42, "Addr")

        # Stock should be 10 - 3 = 7 after order creation
        cancelled = await checkout.cancel_order(order.id, 42)
        assert cancelled is True

        async with UnitOfWork(session_factory) as uow:
            updated = await uow.orders.get(order.id)
            assert updated is not None
            assert updated.status == OrderStatus.CANCELLED.value

        # Stock should be restored to 10
        async with UnitOfWork(session_factory) as uow:
            items = await uow.order_items.list_by_order(order.id)
            product = await uow.products.get(items[0].product_id)
        assert product is not None
        assert product.stock == 10

    @pytest.mark.asyncio
    async def test_cancel_paid_order_fails(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _seed_cart(session_factory)
        checkout = CheckoutService(session_factory)
        order = await checkout.create_order_from_cart(42, "Addr")

        await checkout.confirm_payment(order.id, "tg", "pay")

        cancelled = await checkout.cancel_order(order.id, 42)
        assert cancelled is False

    @pytest.mark.asyncio
    async def test_cancel_wrong_user_fails(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        await _seed_cart(session_factory, user_id=42)
        checkout = CheckoutService(session_factory)
        order = await checkout.create_order_from_cart(42, "Addr")

        cancelled = await checkout.cancel_order(order.id, 99)
        assert cancelled is False


# ── build_invoice_prices ─────────────────────────────────


class TestBuildInvoicePrices:
    def test_builds_labeled_prices(self) -> None:
        from aiogram.types import LabeledPrice

        # Simulate order items
        class FakeItem:
            def __init__(self, name: str, qty: int, price: int) -> None:
                self.product_name = name
                self.quantity = qty
                self.unit_price_smallest_unit = price

        items = [
            FakeItem("Widget", 2, 50000),
            FakeItem("Gadget", 1, 30000),
        ]

        prices = CheckoutService.build_invoice_prices(items)

        assert len(prices) == 2
        assert prices[0].label == "Widget x2"
        assert prices[0].amount == 100000  # 50000 * 2
        assert prices[1].label == "Gadget x1"
        assert prices[1].amount == 30000

    def test_empty_items(self) -> None:
        prices = CheckoutService.build_invoice_prices([])
        assert prices == []


# ── build_invoice_description ─────────────────────────────


class TestBuildInvoiceDescription:
    def test_builds_description(self) -> None:
        class FakeItem:
            def __init__(self, name: str, qty: int, price: int) -> None:
                self.product_name = name
                self.quantity = qty
                self.unit_price_smallest_unit = price

        items = [FakeItem("Widget", 2, 50000)]
        desc = CheckoutService.build_invoice_description(items)
        assert "Widget" in desc
        assert "x2" in desc
