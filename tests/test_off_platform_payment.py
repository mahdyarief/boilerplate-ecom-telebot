"""Tests for the off-platform payment integration (QRIS/Pakasir checkout flow).

These tests cover the new checkout→payment path that uses PaymentService
instead of bot.send_invoice(), as well as the new payment callback handlers
(pay:check, pay:cancel), and the updated Payment model fields.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot_app.app.services.checkout import CheckoutService
from bot_app.core.constants import OrderStatus, PaymentStatus
from bot_app.core.errors import PaymentError
from bot_app.infrastructure.payments.service import PaymentInvoice, PaymentService
from bot_app.infrastructure.persistence.uow import UnitOfWork
from bot_app.shared.money import Money
from bot_app.core.config import settings
from bot_app.features.checkout.texts import (
    fmt_qris_payment_instructions,
    fmt_pakasir_payment_instructions,
    fmt_payment_check_paid,
    fmt_payment_check_pending,
    fmt_payment_cancelled,
)


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:  # type: ignore[valid-type]
    return async_sessionmaker(engine, expire_on_commit=False)


async def _seed_order(
    session_factory: async_sessionmaker[AsyncSession],  # type: ignore[valid-type]
    user_id: int = 42,
    stock: int = 10,
    quantity: int = 1,
    price: int = 100000,
) -> int:
    """Create a seeded order with items and return the order_id."""
    async with UnitOfWork(session_factory) as uow:
        cat = await uow.categories.create(name="TestCat", slug="test-cat-offplat")
        await uow.session.flush()
        prod = await uow.products.create(
            category_id=cat.id, name="Test Product",
            price_smallest_unit=price, stock=stock,
        )
        await uow.session.flush()
        await uow.users.get_or_create(user_id)
        await uow.session.flush()
        await uow.cart_items.add_item(
            user_id=user_id, product_id=prod.id, quantity=quantity,
        )

    checkout = CheckoutService(session_factory)
    order = await checkout.create_order_from_cart(user_id, "Alamat Test")
    return order.id


# ── Payment model new fields ──────────────────────────────


class TestPaymentModelNewFields:
    @pytest.mark.asyncio
    async def test_payment_record_has_qris_fields(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Payment records should store QRIS-specific fields."""
        order_id = await _seed_order(session_factory)

        async with UnitOfWork(session_factory) as uow:
            payment = await uow.payments.create(
                order_id=order_id,
                provider="qris",
                payment_identifier="PAY-ABC12345",
                unique_code=321,
                final_amount=100321,
                qris_payload="000201010211...",
                payment_url=None,
            )

        # Read back and verify
        async with UnitOfWork(session_factory) as uow:
            fetched = await uow.payments.get(payment.id)
            assert fetched is not None
            assert fetched.provider == "qris"
            assert fetched.payment_identifier == "PAY-ABC12345"
            assert fetched.unique_code == 321
            assert fetched.final_amount == 100321
            assert fetched.qris_payload == "000201010211..."
            assert fetched.payment_url is None
            assert fetched.status == PaymentStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_payment_record_has_pakasir_fields(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Payment records should store Pakasir-specific fields."""
        order_id = await _seed_order(session_factory)

        async with UnitOfWork(session_factory) as uow:
            payment = await uow.payments.create(
                order_id=order_id,
                provider="pakasir",
                payment_identifier="PAY-XYZ98765",
                unique_code=0,
                final_amount=100000,
                qris_payload=None,
                payment_url="https://app.pakasir.com/pay/proj/100000?order_id=PAY-XYZ98765",
            )

        async with UnitOfWork(session_factory) as uow:
            fetched = await uow.payments.get(payment.id)
            assert fetched is not None
            assert fetched.provider == "pakasir"
            assert fetched.payment_identifier == "PAY-XYZ98765"
            assert fetched.unique_code == 0
            assert fetched.final_amount == 100000
            assert fetched.qris_payload is None
            assert fetched.payment_url is not None
            assert "pakasir" in fetched.payment_url

    @pytest.mark.asyncio
    async def test_payment_default_fields(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Payment created without QRIS fields should have safe defaults."""
        order_id = await _seed_order(session_factory)

        async with UnitOfWork(session_factory) as uow:
            payment = await uow.payments.create(
                order_id=order_id,
                provider="provider_token",
            )

        async with UnitOfWork(session_factory) as uow:
            fetched = await uow.payments.get(payment.id)
            assert fetched is not None
            assert fetched.unique_code == 0
            assert fetched.final_amount == 0
            assert fetched.qris_payload is None
            assert fetched.payment_url is None
            assert fetched.payment_identifier is None


# ── Payment repository new methods ────────────────────────


class TestPaymentRepositoryNewMethods:
    @pytest.mark.asyncio
    async def test_get_by_identifier(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """get_by_identifier should find a payment by its payment_identifier."""
        order_id = await _seed_order(session_factory)

        async with UnitOfWork(session_factory) as uow:
            await uow.payments.create(
                order_id=order_id,
                provider="qris",
                payment_identifier="PAY-UNIQUE123",
            )

        async with UnitOfWork(session_factory) as uow:
            found = await uow.payments.get_by_identifier("PAY-UNIQUE123")
            assert found is not None
            assert found.order_id == order_id
            assert found.provider == "qris"

            not_found = await uow.payments.get_by_identifier("PAY-NONEXIST")
            assert not_found is None

    @pytest.mark.asyncio
    async def test_get_pending_by_order(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """get_pending_by_order should return the most recent PENDING payment."""
        order_id = await _seed_order(session_factory)

        # Create a PENDING payment
        async with UnitOfWork(session_factory) as uow:
            payment = await uow.payments.create(
                order_id=order_id,
                provider="qris",
                payment_identifier="PAY-PENDING1",
            )

        async with UnitOfWork(session_factory) as uow:
            found = await uow.payments.get_pending_by_order(order_id)
            assert found is not None
            assert found.id == payment.id

    @pytest.mark.asyncio
    async def test_get_pending_by_order_returns_none_when_paid(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """get_pending_by_order should return None if the payment is no longer PENDING."""
        order_id = await _seed_order(session_factory)

        async with UnitOfWork(session_factory) as uow:
            payment = await uow.payments.create(
                order_id=order_id,
                provider="qris",
            )
            await uow.payments.update_status(payment.id, PaymentStatus.SUCCESS)

        async with UnitOfWork(session_factory) as uow:
            found = await uow.payments.get_pending_by_order(order_id)
            assert found is None

    @pytest.mark.asyncio
    async def test_update_invoice_data(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """update_invoice_data should update QRIS fields on an existing payment."""
        order_id = await _seed_order(session_factory)

        async with UnitOfWork(session_factory) as uow:
            payment = await uow.payments.create(
                order_id=order_id,
                provider="qris",
            )

        async with UnitOfWork(session_factory) as uow:
            await uow.payments.update_invoice_data(
                payment.id,
                payment_identifier="PAY-UPDATED1",
                unique_code=456,
                final_amount=100456,
                qris_payload="000201010211updated",
            )

        async with UnitOfWork(session_factory) as uow:
            fetched = await uow.payments.get(payment.id)
            assert fetched is not None
            assert fetched.payment_identifier == "PAY-UPDATED1"
            assert fetched.unique_code == 456
            assert fetched.final_amount == 100456
            assert fetched.qris_payload == "000201010211updated"


# ── CheckoutService.confirm_payment with existing payment ──


class TestConfirmPaymentWithExistingPayment:
    @pytest.mark.asyncio
    async def test_confirm_updates_existing_pending_payment(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """confirm_payment should update an existing PENDING payment to SUCCESS."""
        order_id = await _seed_order(session_factory)

        # Create a PENDING payment record (simulating what checkout router does)
        async with UnitOfWork(session_factory) as uow:
            payment = await uow.payments.create(
                order_id=order_id,
                provider="qris",
                payment_identifier="PAY-QRIS123",
                unique_code=321,
                final_amount=100321,
            )

        checkout = CheckoutService(session_factory)
        await checkout.confirm_payment(
            order_id,
            telegram_charge_id="PAY-QRIS123",
            provider_charge_id="PAY-QRIS123",
            provider_name="qris",
        )

        # Verify the existing payment was updated (not a new one created)
        async with UnitOfWork(session_factory) as uow:
            payments = await uow.payments.get_by_order(order_id)
            assert len(payments) == 1  # Not duplicated
            assert payments[0].status == PaymentStatus.SUCCESS.value
            assert payments[0].provider == "qris"
            assert payments[0].telegram_charge_id == "PAY-QRIS123"
            assert payments[0].provider_charge_id == "PAY-QRIS123"
            # QRIS-specific fields should still be there
            assert payments[0].unique_code == 321
            assert payments[0].final_amount == 100321

    @pytest.mark.asyncio
    async def test_confirm_creates_new_payment_when_none_exists(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """confirm_payment should create a Payment record if none exists (Telegram API path)."""
        order_id = await _seed_order(session_factory)

        checkout = CheckoutService(session_factory)
        await checkout.confirm_payment(
            order_id,
            telegram_charge_id="tg_charge_1",
            provider_charge_id="pay_charge_1",
            provider_name="provider_token",
        )

        async with UnitOfWork(session_factory) as uow:
            payments = await uow.payments.get_by_order(order_id)
            assert len(payments) == 1
            assert payments[0].status == PaymentStatus.SUCCESS.value
            assert payments[0].provider == "provider_token"
            assert payments[0].telegram_charge_id == "tg_charge_1"
            assert payments[0].provider_charge_id == "pay_charge_1"


# ── Text formatting tests ────────────────────────────────


class TestQRISPaymentTexts:
    def test_qris_payment_instructions(self) -> None:
        text = fmt_qris_payment_instructions(
            order_id=5,
            final_amount=50321,
            base_amount=50000,
            unique_code=321,
            currency="IDR",
            provider="qris",
        )
        assert "50.321" in text  # final_amount formatted
        assert "321" in text
        assert "Scan QR" in text
        assert "Cek Pembayaran" in text

    def test_qris_payment_instructions_with_url(self) -> None:
        text = fmt_qris_payment_instructions(
            order_id=5,
            final_amount=50321,
            base_amount=50000,
            unique_code=321,
            currency="IDR",
            provider="qris",
            payment_url="https://pay.example.com",
        )
        assert "https://pay.example.com" in text

    def test_pakasir_payment_instructions(self) -> None:
        text = fmt_pakasir_payment_instructions(
            order_id=5,
            final_amount=100000,
            currency="IDR",
            payment_url="https://app.pakasir.com/pay/proj/100000",
        )
        assert "100.000" in text
        assert "pakasir" in text.lower() or "halaman pembayaran" in text.lower()
        assert "https://app.pakasir.com" in text

    def test_payment_check_paid(self) -> None:
        text = fmt_payment_check_paid(order_id=5, total_smallest_unit=100321, currency="IDR")
        assert "5" in text
        assert "100.321" in text  # formatted IDR
        assert "Diterima" in text

    def test_payment_check_pending(self) -> None:
        text = fmt_payment_check_pending()
        assert "Belum Diterima" in text
        assert "cek lagi" in text.lower()

    def test_payment_cancelled(self) -> None:
        text = fmt_payment_cancelled(order_id=5)
        assert "5" in text
        assert "Dibatalkan" in text
        assert "stok dikembalikan" in text.lower()


# ── Payment action keyboard tests ─────────────────────────


class TestPaymentActionKeyboard:
    def test_payment_action_kb_contains_check_and_cancel(self) -> None:
        from bot_app.shared.keyboards import (
            PREFIX_PAYMENT_CHECK,
            PREFIX_PAYMENT_CANCEL,
            payment_action_kb,
        )

        kb = payment_action_kb(order_id=42)
        buttons = kb.inline_keyboard

        # Should have 2 rows
        assert len(buttons) == 2

        # Check button
        check_text, check_data = buttons[0][0].text, buttons[0][0].callback_data
        assert "Cek Pembayaran" in check_text
        assert check_data == f"{PREFIX_PAYMENT_CHECK}42"

        # Cancel button
        cancel_text, cancel_data = buttons[1][0].text, buttons[1][0].callback_data
        assert "Batalkan" in cancel_text
        assert cancel_data == f"{PREFIX_PAYMENT_CANCEL}42"

    def test_payment_action_kb_custom_texts(self) -> None:
        from bot_app.shared.keyboards import payment_action_kb

        kb = payment_action_kb(
            order_id=99,
            check_text="🔍 Check",
            cancel_text="🗑️ Abort",
        )
        buttons = kb.inline_keyboard
        assert buttons[0][0].text == "🔍 Check"
        assert buttons[1][0].text == "🗑️ Abort"

    def test_callback_data_within_64_bytes(self) -> None:
        """All callback data must be ≤64 bytes (Telegram limit)."""
        from bot_app.shared.keyboards import payment_action_kb

        # Use a large order_id to test edge case
        kb = payment_action_kb(order_id=999999)
        for row in kb.inline_keyboard:
            for button in row:
                assert len(button.callback_data) <= 64


# ── Integration: QRIS checkout flow end-to-end ───────────


class TestQRISCheckoutFlowIntegration:
    @pytest.mark.asyncio
    async def test_full_qris_flow_create_order_and_payment(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Simulate the full QRIS flow: create order → create payment record → confirm."""
        order_id = await _seed_order(session_factory, user_id=42, stock=5, quantity=2, price=75000)

        # Step 1: Set order to AWAITING_PAYMENT
        async with UnitOfWork(session_factory) as uow:
            await uow.orders.update_status(order_id, OrderStatus.AWAITING_PAYMENT)

        # Step 2: Create a payment record with QRIS data (simulating PaymentService)
        async with UnitOfWork(session_factory) as uow:
            payment = await uow.payments.create(
                order_id=order_id,
                provider="qris",
                payment_identifier="PAY-QRISTEST",
                unique_code=456,
                final_amount=150456,  # 75000*2 + 456
                qris_payload="00020101021126380...",
            )

        # Step 3: Verify payment is PENDING
        async with UnitOfWork(session_factory) as uow:
            fetched = await uow.payments.get_pending_by_order(order_id)
            assert fetched is not None
            assert fetched.provider == "qris"
            assert fetched.unique_code == 456
            assert fetched.final_amount == 150456

        # Step 4: Confirm payment (simulating webhook or manual check)
        checkout = CheckoutService(session_factory)
        await checkout.confirm_payment(
            order_id,
            telegram_charge_id="PAY-QRISTEST",
            provider_charge_id="PAY-QRISTEST",
            provider_name="qris",
        )

        # Step 5: Verify final state
        async with UnitOfWork(session_factory) as uow:
            order = await uow.orders.get(order_id)
            assert order is not None
            assert order.status == OrderStatus.PAID.value

            payments = await uow.payments.get_by_order(order_id)
            assert len(payments) == 1
            assert payments[0].status == PaymentStatus.SUCCESS.value
            assert payments[0].unique_code == 456
            assert payments[0].final_amount == 150456

    @pytest.mark.asyncio
    async def test_full_pakasir_flow_create_order_and_payment(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Simulate the full Pakasir flow: create order → create payment record → confirm."""
        order_id = await _seed_order(session_factory, user_id=55, stock=8, quantity=1, price=200000)

        async with UnitOfWork(session_factory) as uow:
            await uow.orders.update_status(order_id, OrderStatus.AWAITING_PAYMENT)

        async with UnitOfWork(session_factory) as uow:
            payment = await uow.payments.create(
                order_id=order_id,
                provider="pakasir",
                payment_identifier="PAY-PAKATEST",
                unique_code=0,
                final_amount=200000,
                qris_payload=None,
                payment_url="https://app.pakasir.com/pay/proj/200000?order_id=PAY-PAKATEST",
            )

        checkout = CheckoutService(session_factory)
        await checkout.confirm_payment(
            order_id,
            telegram_charge_id="PAY-PAKATEST",
            provider_charge_id="PAY-PAKATEST",
            provider_name="pakasir",
        )

        async with UnitOfWork(session_factory) as uow:
            order = await uow.orders.get(order_id)
            assert order is not None
            assert order.status == OrderStatus.PAID.value

            payments = await uow.payments.get_by_order(order_id)
            assert len(payments) == 1
            assert payments[0].status == PaymentStatus.SUCCESS.value
            assert payments[0].provider == "pakasir"
            assert payments[0].payment_url is not None

    @pytest.mark.asyncio
    async def test_cancel_qris_order_releases_stock(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Cancel a QRIS order should release stock (same as any order cancellation)."""
        order_id = await _seed_order(session_factory, user_id=77, stock=3, quantity=2)

        # Verify stock was decremented
        async with UnitOfWork(session_factory) as uow:
            items = await uow.order_items.list_by_order(order_id)
            product = await uow.products.get(items[0].product_id)
            assert product is not None
            assert product.stock == 1  # 3 - 2

        # Cancel the order
        checkout = CheckoutService(session_factory)
        cancelled = await checkout.cancel_order(order_id, 77)
        assert cancelled is True

        # Verify stock was restored
        async with UnitOfWork(session_factory) as uow:
            items = await uow.order_items.list_by_order(order_id)
            product = await uow.products.get(items[0].product_id)
            assert product is not None
            assert product.stock == 3  # restored
