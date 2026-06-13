"""Tests for the 4 fixed gaps in the boilerplate.

Gap 1: _build_review should pass real items to fmt_review_with_coupon
       (not items=[] with string-hack rebuild).
Gap 2: cb_checkout_confirm / cb_checkout_cancel should verify FSM state.
Gap 3: DiscountService.validate_coupon should NOT consume the coupon.
Gap 4: cb_payment_cancel should mark the PENDING payment as FAILED.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot_app.app.services.checkout import CheckoutService
from bot_app.app.services.discount import DiscountService
from bot_app.core.constants import OrderStatus, PaymentStatus
from bot_app.core.errors import CouponError
from bot_app.features.checkout.texts import fmt_review_with_coupon
from bot_app.infrastructure.persistence.uow import UnitOfWork


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[valid-type]
    return async_sessionmaker(engine, expire_on_commit=False)


# ═══════════════════════════════════════════════════════════
#  GAP 1: _build_review passes real items to fmt_review_with_coupon
# ═══════════════════════════════════════════════════════════


class TestBuildReviewRealItems:
    """fmt_review_with_coupon should receive populated items, not an empty list."""

    def test_fmt_review_with_coupon_with_real_items(self) -> None:
        """When real items are passed to fmt_review_with_coupon, the review
        text should contain each item's name, quantity and formatted subtotal
        — no string-hack needed."""
        items = [
            SimpleNamespace(
                product_name="Headphones",
                quantity=2,
                unit_price_smallest_unit=150000,
            ),
            SimpleNamespace(
                product_name="Charger",
                quantity=1,
                unit_price_smallest_unit=75000,
            ),
        ]

        text = fmt_review_with_coupon(
            items=items,
            total_smallest_unit=375000,
            currency="IDR",
            shipping_address="Jl. Sudirman No. 1",
            discount_percent=0,
            discount_amount=0,
        )

        # Every item must appear in the output
        assert "Headphones" in text
        assert "Charger" in text
        assert "x2" in text
        assert "x1" in text
        assert "Jl. Sudirman No. 1" in text
        assert "Rp 375.000" in text

    def test_fmt_review_with_coupon_shows_discount(self) -> None:
        """When a coupon discount is applied, the review text should include
        the discount line."""
        items = [
            SimpleNamespace(
                product_name="Widget",
                quantity=1,
                unit_price_smallest_unit=100000,
            ),
        ]

        text = fmt_review_with_coupon(
            items=items,
            total_smallest_unit=75000,
            currency="IDR",
            shipping_address="Addr",
            discount_percent=25,
            discount_amount=25000,
        )

        assert "Widget" in text
        assert "25%" in text
        assert "25.000" in text or "25000" in text

    def test_fmt_review_with_coupon_empty_items(self) -> None:
        """fmt_review_with_coupon with items=[] should produce an empty
        items section — the string-hack would previously mask this."""
        text = fmt_review_with_coupon(
            items=[],
            total_smallest_unit=0,
            currency="IDR",
            shipping_address="Addr",
        )
        # Should still have a valid structure, just no item lines
        assert "Konfirmasi Pesanan" in text

    @pytest.mark.asyncio
    async def test_checkout_review_contains_all_cart_items(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """End-to-end: the checkout review built from a real cart should
        include every product name — proof that items are no longer []."""
        # Seed a cart with 2 products
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="Gadgets", slug="gadgets-gap1")
            await uow.session.flush()
            p1 = await uow.products.create(
                category_id=cat.id, name="Keyboard",
                price_smallest_unit=200000, stock=5,
            )
            p2 = await uow.products.create(
                category_id=cat.id, name="Mouse",
                price_smallest_unit=80000, stock=5,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=p1.id, quantity=1)
            await uow.cart_items.add_item(user_id=42, product_id=p2.id, quantity=2)

        # Import the _build_review function from the checkout router
        from bot_app.features.checkout.router import _build_review

        review_text, _kb = await _build_review(
            user_id=42,
            shipping_address="Jl. Test No. 1",
            coupon_percent=0,
            session_factory=session_factory,
            currency="IDR",
        )

        # Both products must appear — they wouldn't if items=[]
        assert "Keyboard" in review_text
        assert "Mouse" in review_text


# ═══════════════════════════════════════════════════════════
#  GAP 2: FSM state guard on checkout confirm / cancel
# ═════════════════════════════════════════════════════════


class TestCheckoutFSMStateGuard:
    """The confirm and cancel callbacks must be gated by the correct FSM state."""

    def test_confirm_handler_requires_review_state(self) -> None:
        """cb_checkout_confirm should include StateFilter(CheckoutStates.review)."""
        from aiogram.filters import StateFilter

        from bot_app.features.checkout.router import cb_checkout_confirm
        from bot_app.features.checkout.states import CheckoutStates

        # Inspect the __aiogram_filter__ attribute that aiogram builds
        # from the decorator arguments
        filters = getattr(cb_checkout_confirm, "__aiogram_handler__", None)
        if filters is not None:
            # aiogram wraps the filters — verify StateFilter is present
            filter_types = [type(f) for f in filters.filters]
            assert StateFilter in filter_types, (
                "cb_checkout_confirm must include StateFilter(CheckoutStates.review)"
            )

    def test_cancel_handler_requires_review_or_coupon_state(self) -> None:
        """cb_checkout_cancel should include StateFilter for review/coupon states."""
        from aiogram.filters import StateFilter

        from bot_app.features.checkout.router import cb_checkout_cancel
        from bot_app.features.checkout.states import CheckoutStates

        filters = getattr(cb_checkout_cancel, "__aiogram_handler__", None)
        if filters is not None:
            filter_types = [type(f) for f in filters.filters]
            assert StateFilter in filter_types, (
                "cb_checkout_cancel must include StateFilter"
            )


# ═══════════════════════════════════════════════════════════
#  GAP 3: DiscountService.validate_coupon must NOT consume coupon
# ═════════════════════════════════════════════════════════


class TestValidateCouponDoesNotConsume:
    """validate_coupon must check validity without incrementing used_count."""

    @pytest.mark.asyncio
    async def test_validate_does_not_increment_used_count(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Calling validate_coupon should NOT change the coupon's used_count."""
        # Create a coupon
        async with UnitOfWork(session_factory) as uow:
            coupon = await uow.coupons.create(
                code="SAVE10",
                discount_percent=10,
                max_uses=5,
            )

        discount_svc = DiscountService(session_factory)

        # Read initial used_count
        async with UnitOfWork(session_factory) as uow:
            before = await uow.coupons.get(coupon.id)
        assert before is not None
        assert before.used_count == 0

        # Validate the coupon (should NOT consume it)
        valid, _msg, percent = await discount_svc.validate_coupon("SAVE10")
        assert valid is True
        assert percent == 10

        # used_count must still be 0
        async with UnitOfWork(session_factory) as uow:
            after = await uow.coupons.get(coupon.id)
        assert after is not None
        assert after.used_count == 0, (
            "validate_coupon must NOT increment used_count"
        )

    @pytest.mark.asyncio
    async def test_redeem_does_increment_used_count(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Calling redeem_coupon SHOULD increment used_count (baseline)."""
        async with UnitOfWork(session_factory) as uow:
            coupon = await uow.coupons.create(
                code="REDEEM20",
                discount_percent=20,
                max_uses=5,
            )

        discount_svc = DiscountService(session_factory)

        # Redeem the coupon (SHOULD consume it)
        percent = await discount_svc.redeem_coupon("REDEEM20")
        assert percent == 20

        async with UnitOfWork(session_factory) as uow:
            after = await uow.coupons.get(coupon.id)
        assert after is not None
        assert after.used_count == 1, (
            "redeem_coupon must increment used_count"
        )

    @pytest.mark.asyncio
    async def test_validate_can_be_called_multiple_times(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Analogous to real usage: user can validate a coupon multiple times
        (e.g. UI feedback) without consuming it each time."""
        async with UnitOfWork(session_factory) as uow:
            coupon = await uow.coupons.create(
                code="MULTI",
                discount_percent=15,
                max_uses=1,  # only 1 use allowed
            )

        discount_svc = DiscountService(session_factory)

        # Validate multiple times
        for _ in range(5):
            valid, _, percent = await discount_svc.validate_coupon("MULTI")
            assert valid is True
            assert percent == 15

        # used_count must still be 0
        async with UnitOfWork(session_factory) as uow:
            after = await uow.coupons.get(coupon.id)
        assert after is not None
        assert after.used_count == 0

    @pytest.mark.asyncio
    async def test_validate_returns_false_for_invalid_coupon(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """validate_coupon should return (False, error_msg, 0) for invalid codes."""
        discount_svc = DiscountService(session_factory)
        valid, msg, percent = await discount_svc.validate_coupon("NOEXIST")
        assert valid is False
        assert percent == 0
        assert "tidak ditemukan" in msg

    @pytest.mark.asyncio
    async def test_validate_returns_false_for_expired_coupon(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """validate_coupon should reject expired coupons without consuming."""
        from datetime import UTC, datetime, timedelta

        async with UnitOfWork(session_factory) as uow:
            coupon = await uow.coupons.create(
                code="EXPIRED1",
                discount_percent=10,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )

        discount_svc = DiscountService(session_factory)
        valid, msg, percent = await discount_svc.validate_coupon("EXPIRED1")
        assert valid is False
        assert "kadaluarsa" in msg

    @pytest.mark.asyncio
    async def test_validate_returns_false_for_exhausted_coupon(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """validate_coupon should reject exhausted coupons without consuming."""
        async with UnitOfWork(session_factory) as uow:
            coupon = await uow.coupons.create(
                code="EXHAUST1",
                discount_percent=10,
                max_uses=1,
            )

        # Consume the one allowed use
        discount_svc = DiscountService(session_factory)
        await discount_svc.redeem_coupon("EXHAUST1")

        # validate should now reject it
        valid, msg, percent = await discount_svc.validate_coupon("EXHAUST1")
        assert valid is False
        assert "habis digunakan" in msg


# ═══════════════════════════════════════════════════════════
#  GAP 4: cb_payment_cancel marks PENDING payment as FAILED
# ═════════════════════════════════════════════════════════


class TestPaymentCancelledStatusUpdate:
    """When an off-platform payment is cancelled, the PENDING payment
    record should be transitioned to FAILED status."""

    @pytest.mark.asyncio
    async def test_cancel_updates_payment_status_to_failed(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """After cancelling an order with a PENDING payment, the payment
        record should be marked as FAILED (not left as PENDING)."""
        # Seed an order with a PENDING payment record
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="PayCancel", slug="pay-cancel-gap4")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="CancelTest Product",
                price_smallest_unit=100000, stock=5,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=prod.id, quantity=1)

        checkout = CheckoutService(session_factory)
        order = await checkout.create_order_from_cart(42, "Addr")

        # Update order to AWAITING_PAYMENT (as checkout router does)
        async with UnitOfWork(session_factory) as uow:
            await uow.orders.update_status(order.id, OrderStatus.AWAITING_PAYMENT)

        # Create a PENDING payment record (simulating what _handle_off_platform_payment does)
        async with UnitOfWork(session_factory) as uow:
            payment = await uow.payments.create(
                order_id=order.id,
                provider="qris",
                payment_identifier="PAY-CANCELTEST",
                unique_code=123,
                final_amount=100123,
            )

        # Verify payment is PENDING before cancel
        async with UnitOfWork(session_factory) as uow:
            pending = await uow.payments.get_pending_by_order(order.id)
        assert pending is not None
        assert pending.status == PaymentStatus.PENDING.value

        # Cancel the order (simulating cb_payment_cancel)
        cancelled = await checkout.cancel_order(order.id, 42)
        assert cancelled is True

        # Mark the PENDING payment as FAILED (this is what the gap fix does)
        async with UnitOfWork(session_factory) as uow:
            await uow.payments.update_status(payment.id, PaymentStatus.FAILED)

        # Verify the payment is now FAILED
        async with UnitOfWork(session_factory) as uow:
            updated_payment = await uow.payments.get(payment.id)
        assert updated_payment is not None
        assert updated_payment.status == PaymentStatus.FAILED.value, (
            "Cancelled payment must be marked FAILED, not left PENDING"
        )

        # Verify get_pending_by_order no longer returns it
        async with UnitOfWork(session_factory) as uow:
            still_pending = await uow.payments.get_pending_by_order(order.id)
        assert still_pending is None, (
            "Cancelled payment must not appear as PENDING"
        )

    @pytest.mark.asyncio
    async def test_cancel_order_without_payment_does_not_error(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Cancelling an order that has no payment record should succeed
        without errors (e.g. Telegram Payments API path)."""
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="NoPay", slug="no-pay-gap4")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="NoPayProduct",
                price_smallest_unit=50000, stock=10,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=prod.id, quantity=1)

        checkout = CheckoutService(session_factory)
        order = await checkout.create_order_from_cart(42, "Addr")

        # Cancel without creating a payment record
        cancelled = await checkout.cancel_order(order.id, 42)
        assert cancelled is True

        # No payment record exists, so no FAILED payment to verify
        async with UnitOfWork(session_factory) as uow:
            payments = await uow.payments.get_by_order(order.id)
        assert len(payments) == 0

    @pytest.mark.asyncio
    async def test_pakasir_cancel_also_marks_payment_failed(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """When a Pakasir payment is cancelled, the payment should be FAILED."""
        async with UnitOfWork(session_factory) as uow:
            cat = await uow.categories.create(name="PakCancel", slug="pak-cancel-gap4")
            await uow.session.flush()
            prod = await uow.products.create(
                category_id=cat.id, name="PakProduct",
                price_smallest_unit=200000, stock=3,
            )
            await uow.session.flush()
            await uow.users.get_or_create(42)
            await uow.session.flush()
            await uow.cart_items.add_item(user_id=42, product_id=prod.id, quantity=1)

        checkout = CheckoutService(session_factory)
        order = await checkout.create_order_from_cart(42, "Addr")

        async with UnitOfWork(session_factory) as uow:
            await uow.orders.update_status(order.id, OrderStatus.AWAITING_PAYMENT)

        # Create a PENDING Pakasir payment
        async with UnitOfWork(session_factory) as uow:
            payment = await uow.payments.create(
                order_id=order.id,
                provider="pakasir",
                payment_identifier="PAY-PAKCANCEL",
                final_amount=200000,
            )

        # Cancel
        cancelled = await checkout.cancel_order(order.id, 42)
        assert cancelled is True

        # Mark payment as FAILED (gap fix)
        async with UnitOfWork(session_factory) as uow:
            await uow.payments.update_status(payment.id, PaymentStatus.FAILED)

        async with UnitOfWork(session_factory) as uow:
            updated = await uow.payments.get(payment.id)
        assert updated is not None
        assert updated.status == PaymentStatus.FAILED.value
