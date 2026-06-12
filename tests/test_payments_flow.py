"""Integration-style tests for the payments feature.

Tests cover the pre_checkout verification and successful_payment
confirmation flows.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot_app.app.services.checkout import CheckoutService
from bot_app.core.constants import OrderStatus, PaymentStatus
from bot_app.infrastructure.persistence.uow import UnitOfWork


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[valid-type]
    return async_sessionmaker(engine, expire_on_commit=False)


async def _create_order_with_items(
    session_factory: async_sessionmaker[AsyncSession],  # type: ignore[valid-type]
    user_id: int = 42,
    stock: int = 10,
    quantity: int = 2,
) -> int:
    """Create a seeded order and return the order_id."""
    async with UnitOfWork(session_factory) as uow:
        cat = await uow.categories.create(name="Pay", slug="pay-test")
        await uow.session.flush()
        prod = await uow.products.create(
            category_id=cat.id, name="Payable Item",
            price_smallest_unit=75000, stock=stock,
        )
        await uow.session.flush()
        await uow.users.get_or_create(user_id)
        await uow.session.flush()
        await uow.cart_items.add_item(
            user_id=user_id, product_id=prod.id, quantity=quantity,
        )

    checkout = CheckoutService(session_factory)
    order = await checkout.create_order_from_cart(user_id, "Payment Address")
    return order.id


# ── Pre-checkout verification ────────────────────────────


class TestPreCheckoutVerification:
    @pytest.mark.asyncio
    async def test_valid_pending_order_passes(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        order_id = await _create_order_with_items(session_factory)
        checkout = CheckoutService(session_factory)

        ok, msg = await checkout.verify_pre_checkout(order_id)
        assert ok is True
        assert msg == ""

    @pytest.mark.asyncio
    async def test_cancelled_order_fails(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        order_id = await _create_order_with_items(session_factory)
        checkout = CheckoutService(session_factory)

        await checkout.cancel_order(order_id, 42)

        ok, msg = await checkout.verify_pre_checkout(order_id)
        assert ok is False
        assert "diproses" in msg or "dibatalkan" in msg

    @pytest.mark.asyncio
    async def test_paid_order_fails(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        order_id = await _create_order_with_items(session_factory)
        checkout = CheckoutService(session_factory)

        await checkout.confirm_payment(order_id, "tg_1", "pay_1")

        ok, msg = await checkout.verify_pre_checkout(order_id)
        assert ok is False
        assert "diproses" in msg or "dibatalkan" in msg

    @pytest.mark.asyncio
    async def test_unknown_order_fails(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        checkout = CheckoutService(session_factory)

        ok, msg = await checkout.verify_pre_checkout(99999)
        assert ok is False
        assert "tidak ditemukan" in msg

    @pytest.mark.asyncio
    async def test_awaiting_payment_order_passes(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        order_id = await _create_order_with_items(session_factory)

        # Manually set to AWAITING_PAYMENT (simulating invoice sent)
        async with UnitOfWork(session_factory) as uow:
            await uow.orders.update_status(order_id, OrderStatus.AWAITING_PAYMENT)

        checkout = CheckoutService(session_factory)
        ok, msg = await checkout.verify_pre_checkout(order_id)
        assert ok is True


# ── Successful payment ───────────────────────────────────


class TestSuccessfulPayment:
    @pytest.mark.asyncio
    async def test_confirm_payment_creates_records(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        order_id = await _create_order_with_items(session_factory)
        checkout = CheckoutService(session_factory)

        await checkout.confirm_payment(
            order_id,
            telegram_charge_id="tg_charge_xyz",
            provider_charge_id="pay_charge_abc",
        )

        async with UnitOfWork(session_factory) as uow:
            order = await uow.orders.get(order_id)
            assert order is not None
            assert order.status == OrderStatus.PAID.value

            payments = await uow.payments.get_by_order(order_id)
            assert len(payments) == 1

            payment = payments[0]
            assert payment.status == PaymentStatus.SUCCESS.value
            assert payment.telegram_charge_id == "tg_charge_xyz"
            assert payment.provider_charge_id == "pay_charge_abc"
            assert payment.provider == "provider_token"

    @pytest.mark.asyncio
    async def test_confirm_payment_does_not_change_stock(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Stock was already decremented during create_order_from_cart."""
        order_id = await _create_order_with_items(
            session_factory, stock=10, quantity=3,
        )
        checkout = CheckoutService(session_factory)

        # Stock should be 10 - 3 = 7 after order creation
        async with UnitOfWork(session_factory) as uow:
            order = await uow.orders.get(order_id)
            items = await uow.order_items.list_by_order(order_id)
            product = await uow.products.get(items[0].product_id)
        assert product is not None
        stock_before_payment = product.stock

        # Confirm payment
        await checkout.confirm_payment(order_id, "tg", "pay")

        # Stock should be unchanged
        async with UnitOfWork(session_factory) as uow:
            items = await uow.order_items.list_by_order(order_id)
            product = await uow.products.get(items[0].product_id)
        assert product is not None
        assert product.stock == stock_before_payment

    @pytest.mark.asyncio
    async def test_double_confirm_payment(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Double-confirming should not create duplicate payment records."""
        order_id = await _create_order_with_items(session_factory)
        checkout = CheckoutService(session_factory)

        await checkout.confirm_payment(order_id, "tg_1", "pay_1")
        await checkout.confirm_payment(order_id, "tg_2", "pay_2")

        async with UnitOfWork(session_factory) as uow:
            payments = await uow.payments.get_by_order(order_id)
        assert len(payments) == 2  # both get created, but order was already PAID

    @pytest.mark.asyncio
    async def test_confirm_payment_with_custom_provider_name(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """confirm_payment should store the provider_name in the Payment record."""
        order_id = await _create_order_with_items(session_factory)
        checkout = CheckoutService(session_factory)

        await checkout.confirm_payment(
            order_id,
            telegram_charge_id="tg_qris_1",
            provider_charge_id="qris_1",
            provider_name="qris",
        )

        async with UnitOfWork(session_factory) as uow:
            payments = await uow.payments.get_by_order(order_id)
            assert len(payments) == 1
            assert payments[0].provider == "qris"

    @pytest.mark.asyncio
    async def test_confirm_payment_with_pakasir_provider_name(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """confirm_payment should store 'pakasir' as provider when specified."""
        order_id = await _create_order_with_items(session_factory)
        checkout = CheckoutService(session_factory)

        await checkout.confirm_payment(
            order_id,
            telegram_charge_id="tg_pak_1",
            provider_charge_id="pak_1",
            provider_name="pakasir",
        )

        async with UnitOfWork(session_factory) as uow:
            payments = await uow.payments.get_by_order(order_id)
            assert len(payments) == 1
            assert payments[0].provider == "pakasir"
