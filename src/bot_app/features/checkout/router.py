"""Checkout router — FSM-driven checkout flow: address → review → pay.

Interaction flow (all via inline keyboards + FSM):

1. ``/checkout`` or ``cko:start``  →  ask shipping address (FSM: address)
2. User types address  →  show coupon prompt (FSM: coupon_code)
3. User applies/skips coupon  →  show review (FSM: review)
4. ``cko:confirm``  →  reserve stock, create order, send payment (FSM: paying)
5. ``cko:cancel``  →  cancel, return to cart

Payment lifecycle depends on the active provider:

- **QRIS / Pakasir**: a QR code + payment instructions are sent inline;
  the user presses "Check Payment" to poll or "Cancel" to abort.
  Payment confirmation happens via webhook or manual check.
- **Telegram Payments API** (``PROVIDER_TOKEN``): a native invoice is sent;
  Telegram handles ``pre_checkout_query`` and ``successful_payment``.
- **Dev mode**: when nothing is configured, the order is auto-confirmed.

Callback-data schema (all ≤64 bytes):

* ``cko:start``    — start checkout
* ``cko:confirm``  — confirm and pay
* ``cko:cancel``   — cancel checkout
* ``pay:check:<order_id>``  — check off-platform payment status
* ``pay:cancel:<order_id>`` — cancel off-platform payment
"""

from __future__ import annotations

import logging
from io import BytesIO

from aiogram import Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from ...app.services.checkout import CheckoutService
from ...app.services.discount import DiscountService
from ...app.services.pricing import LineItem, compute_total
from ...app.services.wallet import WalletService
from ...core.config import settings
from ...core.constants import OrderStatus, PaymentStatus
from ...core.errors import CouponError, NotFoundError, PaymentError, StockError, WalletError
from ...infrastructure.payments.service import PaymentService
from ...infrastructure.persistence.uow import UnitOfWork
from .states import CheckoutStates
from .texts import (
    fmt_checkout_coupon_prompt,
    fmt_coupon_applied,
    fmt_coupon_invalid,
    fmt_payment_cancelled,
    fmt_pakasir_payment_instructions,
    fmt_payment_check_paid,
    fmt_payment_check_pending,
    fmt_qris_payment_instructions,
    fmt_review_with_coupon,
    fmt_wallet_payment_option,
    fmt_wallet_payment_success,
)

logger = logging.getLogger(__name__)

router = Router(name="checkout")

# ── Callback data prefixes ────────────────────────────────

_CHECKOUT_PREFIX = "cko:"


# ── Helpers ───────────────────────────────────────────────


async def _ensure_cart_not_empty(
    user_id: int,
    session_factory,
) -> bool:
    """Return ``True`` if the user has items in their cart."""
    async with UnitOfWork(session_factory) as uow:
        count = await uow.cart_items.count_items(user_id)
    return count > 0


async def _send_qris_qr(
    bot: types.Bot,
    chat_id: int,
    qris_payload: str,
) -> None:
    """Generate a QR code image from the QRIS payload and send it as a photo.

    Falls back to sending the raw QRIS string if qrcode library is not available.
    """
    try:
        import qrcode as qrcode_lib  # type: ignore[import-untyped]

        img = qrcode_lib.make(qris_payload)
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        await bot.send_photo(
            chat_id=chat_id,
            photo=types.BufferedInputFile(buf, filename="qris.png"),
            caption="📱 Scan QR code ini untuk membayar:",
        )
    except ImportError:
        logger.warning("qrcode library not installed — sending raw QRIS payload instead")
        await bot.send_message(
            chat_id=chat_id,
            text=f"📱 QRIS Payload:\n<code>{qris_payload}</code>",
            parse_mode="HTML",
        )


# ── Command handler ──────────────────────────────────────


@router.message(Command("checkout"))
async def cmd_checkout(
    message: types.Message,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Start the checkout flow — ask for shipping address."""
    user_id = message.from_user.id

    # Ensure user exists
    async with UnitOfWork(session_factory) as uow:
        await uow.users.get_or_create(user_id)

    if not await _ensure_cart_not_empty(user_id, session_factory):
        await message.answer("🛒 Keranjang Anda kosong. Ketik /catalog untuk mulai belanja!")
        return

    # Clean up any expired reservations before checking out
    checkout = CheckoutService(session_factory)
    await checkout.release_expired_reservations()

    await state.set_state(CheckoutStates.address)
    await message.answer(
        "📦 **Checkout**\n\n"
        "Silakan ketik alamat pengiriman Anda:"
    )


# ── Callback: start checkout from cart button ────────────


@router.callback_query(lambda c: c.data == f"{_CHECKOUT_PREFIX}start")
async def cb_checkout_start(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Start checkout from the cart's \"💳 Checkout\" button."""
    user_id = callback.from_user.id

    if not await _ensure_cart_not_empty(user_id, session_factory):
        await callback.answer("🛒 Keranjang kosong!", show_alert=True)
        return

    # Clean up any expired reservations
    checkout = CheckoutService(session_factory)
    await checkout.release_expired_reservations()

    await state.set_state(CheckoutStates.address)
    await callback.message.answer(
        "📦 **Checkout**\n\n"
        "Silakan ketik alamat pengiriman Anda:"
    )
    await callback.answer()


# ── FSM: Address ─────────────────────────────────────────


@router.message(StateFilter(CheckoutStates.address))
async def process_address(
    message: types.Message,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """User typed their shipping address — show coupon prompt."""
    if not message.text:
        await message.answer("⚠️ Silakan ketik alamat pengiriman Anda sebagai teks.")
        return

    shipping_address = message.text.strip()
    if len(shipping_address) < 5:
        await message.answer("⚠️ Alamat terlalu pendek. Silakan ketik alamat lengkap Anda.")
        return

    user_id = message.from_user.id

    # Build order review from cart
    async with UnitOfWork(session_factory) as uow:
        cart_items = await uow.cart_items.list_by_user(user_id)

    if not cart_items:
        await state.clear()
        await message.answer("🛒 Keranjang Anda kosong. Ketik /catalog untuk mulai belanja!")
        return

    # Save address in FSM data for later use
    await state.update_data(shipping_address=shipping_address)
    await state.set_state(CheckoutStates.coupon_code)

    from ...shared.keyboards import checkout_coupon_kb
    kb = checkout_coupon_kb()
    await message.answer(fmt_checkout_coupon_prompt(), reply_markup=kb)


# ── FSM: Coupon Code ─────────────────────────────────────


@router.callback_query(lambda c: c.data == "cko_coupon:apply", StateFilter(CheckoutStates.coupon_code))
async def cb_checkout_coupon_apply(
    callback: types.CallbackQuery,
    state: FSMContext,
) -> None:
    """User wants to apply a coupon → ask them to type the code."""
    await callback.message.answer(
        "🎟️ Ketik kode kupon Anda:"
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "cko_coupon:skip", StateFilter(CheckoutStates.coupon_code))
async def cb_checkout_coupon_skip(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """User skips the coupon → show review with no discount."""
    await state.update_data(coupon_percent=0)
    await _show_review(callback, state, session_factory)


@router.message(StateFilter(CheckoutStates.coupon_code))
async def process_coupon_code(
    message: types.Message,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """User typed a coupon code → validate and show review."""
    if not message.text:
        await message.answer("⚠️ Ketik kode kupon atau tekan /skip.")
        return

    code = message.text.strip()
    if code == "/skip":
        await state.update_data(coupon_percent=0)
        await _show_review_message(message, state, session_factory)
        return

    discount_service = DiscountService(session_factory)
    try:
        percent = await discount_service.redeem_coupon(code)
        await state.update_data(coupon_percent=percent)
        await message.answer(fmt_coupon_applied(percent, settings.CURRENCY, 0))
    except CouponError as exc:
        await message.answer(fmt_coupon_invalid(str(exc)))
        # Stay in the same state so user can retry or skip
        from ...shared.keyboards import checkout_coupon_kb
        kb = checkout_coupon_kb()
        await message.answer("Coba lagi atau lewati:", reply_markup=kb)
        return

    await _show_review_message(message, state, session_factory)


# ── Review helpers ──────────────────────────────────────


async def _show_review(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,
) -> None:
    """Build and show the checkout review from the callback context."""
    user_id = callback.from_user.id
    data = await state.get_data()
    shipping_address = data.get("shipping_address", "")
    coupon_percent = data.get("coupon_percent", 0)

    review_text, kb = await _build_review(
        user_id, shipping_address, coupon_percent,
        session_factory, settings.CURRENCY,
    )

    await state.set_state(CheckoutStates.review)
    try:
        await callback.message.edit_text(review_text, reply_markup=kb)
    except Exception:
        await callback.message.answer(review_text, reply_markup=kb)
    await callback.answer()


async def _show_review_message(
    message: types.Message,
    state: FSMContext,
    session_factory,
) -> None:
    """Build and show the checkout review from a message context."""
    user_id = message.from_user.id
    data = await state.get_data()
    shipping_address = data.get("shipping_address", "")
    coupon_percent = data.get("coupon_percent", 0)

    review_text, kb = await _build_review(
        user_id, shipping_address, coupon_percent,
        session_factory, settings.CURRENCY,
    )

    await state.set_state(CheckoutStates.review)
    await message.answer(review_text, reply_markup=kb)


async def _build_review(
    user_id: int,
    shipping_address: str,
    coupon_percent: int,
    session_factory,
    currency: str,
) -> tuple[str, object]:
    """Build the checkout review text and keyboard."""
    from types import SimpleNamespace

    from ...shared.keyboards import checkout_confirm_kb
    from ...shared.money import Money

    line_items: list[LineItem] = []
    review_items: list[SimpleNamespace] = []  # items for fmt_review_with_coupon

    async with UnitOfWork(session_factory) as uow:
        cart_items = await uow.cart_items.list_by_user(user_id)
        for item in cart_items:
            product = await uow.products.get(item.product_id)
            if product is None:
                continue
            unit_price = Money(product.price_smallest_unit, currency)
            line_items.append(LineItem(unit_price=unit_price, quantity=item.quantity))
            review_items.append(SimpleNamespace(
                product_name=product.name,
                quantity=item.quantity,
                unit_price_smallest_unit=product.price_smallest_unit,
            ))

    breakdown = compute_total(line_items, currency, coupon_percent=coupon_percent)
    discount_amount = breakdown.discount.amount_minor

    total = breakdown.total

    review_text = fmt_review_with_coupon(
        items=review_items,
        total_smallest_unit=total.amount_minor,
        currency=currency,
        shipping_address=shipping_address,
        discount_percent=coupon_percent,
        discount_amount=discount_amount,
    )

    kb = checkout_confirm_kb()
    return review_text, kb


# ── FSM: Review — Confirm ───────────────────────────────


@router.callback_query(lambda c: c.data == f"{_CHECKOUT_PREFIX}confirm", StateFilter(CheckoutStates.review))
async def cb_checkout_confirm(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Confirm checkout — create order, reserve stock, initiate payment.

    Payment path is determined by the active provider:

    1. **Wallet** → pay instantly from user's saldo
    2. **QRIS / Pakasir** → create invoice via PaymentService, send QR + instructions
    3. **Telegram Payments API** (PROVIDER_TOKEN) → send native Telegram invoice
    4. **Dev mode** (nothing configured) → auto-confirm order
    """
    user_id = callback.from_user.id

    data = await state.get_data()
    shipping_address = data.get("shipping_address", "")
    coupon_percent = data.get("coupon_percent", 0)
    if not shipping_address:
        await state.clear()
        await callback.answer("❌ Sesi checkout kadaluarsa. Silakan coba lagi.", show_alert=True)
        return

    checkout = CheckoutService(session_factory)

    try:
        order = await checkout.create_order_from_cart(
            user_id, shipping_address, coupon_percent=coupon_percent,
        )
    except NotFoundError as exc:
        await state.clear()
        await callback.answer(f"❌ {exc}", show_alert=True)
        return
    except StockError as exc:
        await state.clear()
        await callback.answer(f"⚠️ {exc}", show_alert=True)
        return

    # Update order status to AWAITING_PAYMENT
    async with UnitOfWork(session_factory) as uow:
        await uow.orders.update_status(order.id, OrderStatus.AWAITING_PAYMENT)

    # ── Determine payment path ─────────────────────────────
    # Check if the user wants to pay via wallet (FSM data)
    payment_method = data.get("payment_method", "auto")

    # ── Path 1: Wallet payment (saldo) ────────────────────────
    if payment_method == "wallet":
        await _handle_wallet_payment(
            callback, state, session_factory, checkout,
            order, user_id,
        )
        # Clean up PaymentService resources
        try:
            payment_svc = PaymentService()
            await payment_svc.close()
        except Exception:
            pass
        return

    # ── Auto-select: if wallet has enough balance, offer wallet payment ──
    if payment_method == "auto":
        wallet_svc = WalletService(session_factory)
        try:
            balance = await wallet_svc.get_balance(user_id)
            if balance >= order.total_smallest_unit:
                # Show payment method selection keyboard
                await state.update_data(order_id=order.id)
                await state.set_state(CheckoutStates.paying)
                from ...shared.keyboards import payment_method_select_kb
                kb = payment_method_select_kb(order.id, balance, order.total_smallest_unit, settings.CURRENCY)
                await callback.message.answer(
                    fmt_wallet_payment_option(balance, order.total_smallest_unit, settings.CURRENCY),
                    reply_markup=kb,
                )
                await callback.answer("💳 Pilih metode pembayaran!")
                # Clean up
                try:
                    payment_svc = PaymentService()
                    await payment_svc.close()
                except Exception:
                    pass
                return
        except Exception:
            pass  # Fall through to other payment methods

    # ── Path 2: QRIS / Pakasir (off-platform) ───────────────
    payment_svc = PaymentService()
    provider = payment_svc.active_provider

    if provider in ("qris", "pakasir"):
        await _handle_off_platform_payment(
            callback, state, session_factory, checkout,
            order, payment_svc, provider, user_id,
        )
    # ── Path 3: Telegram Payments API (PROVIDER_TOKEN) ──────
    elif provider == "provider_token":
        await _handle_telegram_invoice(
            callback, state, session_factory, checkout, order, user_id,
        )
    # ── Path 4: Dev mode (nothing configured) ───────────────
    else:
        logger.warning(
            "No payment provider configured — auto-confirming order %d", order.id,
        )
        await checkout.confirm_payment(
            order.id,
            telegram_charge_id=f"dev_auto_{order.id}",
            provider_charge_id=f"dev_auto_{order.id}",
        )
        await state.clear()
        from .texts import fmt_payment_success
        await callback.message.answer(
            fmt_payment_success(order.id, order.total_smallest_unit, settings.CURRENCY)
        )
        await callback.answer("✅ Pesanan dibuat (mode dev — auto dikonfirmasi).")

    # Clean up PaymentService resources
    try:
        await payment_svc.close()
    except Exception:
        pass


async def _handle_off_platform_payment(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,
    checkout: CheckoutService,
    order,
    payment_svc: PaymentService,
    provider: str,
    user_id: int,
) -> None:
    """Handle QRIS or Pakasir payment: create invoice, send QR + instructions."""
    try:
        invoice = await payment_svc.create_invoice(
            order_id=order.id,
            amount=order.total_smallest_unit,
        )
    except PaymentError as exc:
        logger.error("create_invoice failed for order %d: %s", order.id, exc)
        # Release stock since we can't collect payment
        await checkout.cancel_order(order.id, user_id)
        await state.clear()
        await callback.answer("❌ Gagal membuat invoice pembayaran. Stok dikembalikan.", show_alert=True)
        return
    except Exception as exc:
        logger.error("create_invoice unexpected error for order %d: %s", order.id, exc)
        await checkout.cancel_order(order.id, user_id)
        await state.clear()
        await callback.answer("❌ Gagal membuat invoice pembayaran. Stok dikembalikan.", show_alert=True)
        return

    # Persist the invoice data in a Payment record
    async with UnitOfWork(session_factory) as uow:
        payment = await uow.payments.create(
            order_id=order.id,
            provider=invoice.provider,
            payment_identifier=invoice.payment_identifier,
            unique_code=invoice.unique_code,
            final_amount=invoice.final_amount,
            qris_payload=invoice.qris_payload,
            payment_url=invoice.payment_url,
        )

    # Build and send payment instructions
    if provider == "pakasir" and invoice.payment_url:
        text = fmt_pakasir_payment_instructions(
            order_id=order.id,
            final_amount=invoice.final_amount,
            currency=settings.CURRENCY,
            payment_url=invoice.payment_url,
        )
        # Also send QRIS payload as QR if available
        if invoice.qris_payload:
            await callback.message.answer(text)
            await _send_qris_qr(callback.bot, user_id, invoice.qris_payload)
        else:
            from ...shared.keyboards import payment_action_kb
            kb = payment_action_kb(order.id)
            await callback.message.answer(text, reply_markup=kb)
    else:
        # Direct QRIS
        text = fmt_qris_payment_instructions(
            order_id=order.id,
            final_amount=invoice.final_amount,
            base_amount=invoice.amount,
            unique_code=invoice.unique_code,
            currency=settings.CURRENCY,
            provider=invoice.provider,
            payment_url=invoice.payment_url,
        )
        await callback.message.answer(text)
        if invoice.qris_payload:
            await _send_qris_qr(callback.bot, user_id, invoice.qris_payload)

    # Send action keyboard separately (after the QR image if any)
    from ...shared.keyboards import payment_action_kb
    kb = payment_action_kb(order.id)
    await callback.message.answer(
        "📝 Setelah melakukan pembayaran, tekan tombol di bawah:",
        reply_markup=kb,
    )

    await state.set_state(CheckoutStates.paying)
    await state.update_data(order_id=order.id)
    await callback.answer("💳 Invoice pembayaran dikirim!")


async def _handle_telegram_invoice(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,
    checkout: CheckoutService,
    order,
    user_id: int,
) -> None:
    """Handle Telegram Payments API: send a native invoice via send_invoice."""
    # Load order items for the invoice
    async with UnitOfWork(session_factory) as uow:
        order_items = await uow.order_items.list_by_order(order.id)

    prices = CheckoutService.build_invoice_prices(order_items)
    description = CheckoutService.build_invoice_description(order_items)

    try:
        await callback.bot.send_invoice(
            chat_id=user_id,
            title=f"Pesanan #{order.id}",
            description=description,
            payload=str(order.id),
            provider_token=settings.PROVIDER_TOKEN,
            currency=settings.CURRENCY,
            prices=prices,
        )
    except Exception as exc:
        logger.error("send_invoice failed for order %d: %s", order.id, exc)
        # Release stock since we can't collect payment
        await checkout.cancel_order(order.id, user_id)
        await state.clear()
        await callback.answer("❌ Gagal mengirim invoice. Stok dikembalikan.", show_alert=True)
        return

    await state.set_state(CheckoutStates.paying)
    await state.update_data(order_id=order.id)
    await callback.answer("💳 Invoice dikirim! Silakan lakukan pembayaran.")


async def _handle_wallet_payment(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,
    checkout: CheckoutService,
    order,
    user_id: int,
) -> None:
    """Handle wallet (saldo) payment: debit wallet, mark order as PAID instantly."""
    wallet_svc = WalletService(session_factory)

    try:
        new_balance = await checkout.pay_with_wallet(order.id, user_id)
    except WalletError as exc:
        # Wallet has insufficient balance — release stock and cancel
        await checkout.cancel_order(order.id, user_id)
        await state.clear()
        await callback.answer(f"❌ {exc}", show_alert=True)
        return
    except NotFoundError as exc:
        await checkout.cancel_order(order.id, user_id)
        await state.clear()
        await callback.answer(f"❌ {exc}", show_alert=True)
        return
    except Exception as exc:
        logger.error("wallet payment failed for order %d: %s", order.id, exc)
        await checkout.cancel_order(order.id, user_id)
        await state.clear()
        await callback.answer("❌ Gagal memproses pembayaran saldo. Stok dikembalikan.", show_alert=True)
        return

    await state.clear()
    from .texts import fmt_wallet_payment_success
    await callback.message.answer(
        fmt_wallet_payment_success(
            order.id, order.total_smallest_unit, settings.CURRENCY, new_balance,
        )
    )
    await callback.answer("✅ Pembayaran saldo berhasil!")

    # Notify admins of low stock
    try:
        from ...features.payments.router import _notify_low_stock
        await _notify_low_stock(callback.bot, session_factory)
    except Exception:
        pass


# ── Payment method selection (wallet vs other) ──────────


@router.callback_query(lambda c: c.data and c.data.startswith("paym:wallet:"), StateFilter(CheckoutStates.paying))
async def cb_pay_method_wallet(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """User chose to pay with wallet (saldo)."""
    assert callback.data is not None
    payload = callback.data[len("paym:wallet:"):]
    if not payload.isdigit():
        await callback.answer("❌ Data pesanan tidak valid.", show_alert=True)
        return

    order_id = int(payload)
    user_id = callback.from_user.id
    checkout = CheckoutService(session_factory)

    try:
        new_balance = await checkout.pay_with_wallet(order_id, user_id)
    except WalletError as exc:
        await callback.answer(f"❌ {exc}", show_alert=True)
        return
    except NotFoundError as exc:
        await callback.answer(f"❌ {exc}", show_alert=True)
        return
    except Exception as exc:
        logger.error("wallet payment failed for order %d: %s", order_id, exc)
        await callback.answer("❌ Gagal memproses pembayaran saldo.", show_alert=True)
        return

    await state.clear()

    async with UnitOfWork(session_factory) as uow:
        order = await uow.orders.get(order_id)

    if order is None:
        total = 0
    else:
        total = order.total_smallest_unit

    await callback.message.answer(
        fmt_wallet_payment_success(order_id, total, settings.CURRENCY, new_balance)
    )
    await callback.answer("✅ Pembayaran saldo berhasil!")

    # Notify admins of low stock
    try:
        from ...features.payments.router import _notify_low_stock
        await _notify_low_stock(callback.bot, session_factory)
    except Exception:
        pass


@router.callback_query(lambda c: c.data and c.data.startswith("paym:other:"), StateFilter(CheckoutStates.paying))
async def cb_pay_method_other(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """User chose to pay with another method (QRIS/Pakasir/Telegram invoice)."""
    assert callback.data is not None
    payload = callback.data[len("paym:other:"):]
    if not payload.isdigit():
        await callback.answer("❌ Data pesanan tidak valid.", show_alert=True)
        return

    order_id = int(payload)
    user_id = callback.from_user.id

    # Determine the external payment provider
    payment_svc = PaymentService()
    provider = payment_svc.active_provider

    checkout = CheckoutService(session_factory)

    # Reload order
    async with UnitOfWork(session_factory) as uow:
        order = await uow.orders.get(order_id)

    if order is None:
        await callback.answer("❌ Pesanan tidak ditemukan.", show_alert=True)
        try:
            await payment_svc.close()
        except Exception:
            pass
        return

    if provider in ("qris", "pakasir"):
        await _handle_off_platform_payment(
            callback, state, session_factory, checkout,
            order, payment_svc, provider, user_id,
        )
    elif provider == "provider_token":
        await _handle_telegram_invoice(
            callback, state, session_factory, checkout, order, user_id,
        )
    else:
        # Dev mode auto-confirm
        logger.warning(
            "No payment provider configured — auto-confirming order %d", order.id,
        )
        await checkout.confirm_payment(
            order.id,
            telegram_charge_id=f"dev_auto_{order.id}",
            provider_charge_id=f"dev_auto_{order.id}",
        )
        await state.clear()
        from .texts import fmt_payment_success
        await callback.message.answer(
            fmt_payment_success(order.id, order.total_smallest_unit, settings.CURRENCY)
        )
        await callback.answer("✅ Pesanan dibuat (mode dev — auto dikonfirmasi).")
        try:
            await payment_svc.close()
        except Exception:
            pass


# ── FSM: Review — Cancel ────────────────────────────────


@router.callback_query(lambda c: c.data == f"{_CHECKOUT_PREFIX}cancel", StateFilter(CheckoutStates.review, CheckoutStates.coupon_code))
async def cb_checkout_cancel(
    callback: types.CallbackQuery,
    state: FSMContext,
) -> None:
    """Cancel the checkout flow and return to cart view."""
    await state.clear()
    await callback.message.answer(
        "❌ Checkout dibatalkan.\n\n"
        "Ketik /cart untuk melihat keranjang Anda."
    )
    await callback.answer("Dibatalkan.")


# ── Payment actions: Check & Cancel (off-platform) ──────


@router.callback_query(lambda c: c.data and c.data.startswith("pay:check:"))
async def cb_payment_check(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Check whether an off-platform (QRIS/Pakasir) payment has been received.

    For Pakasir, we query the gateway. For direct QRIS, we check if the
    order status has been updated (e.g. by a webhook or admin confirmation).
    """
    order_id_str = callback.data.split(":")[-1]  # type: ignore[union-attr]
    if not order_id_str or not order_id_str.isdigit():
        await callback.answer("❌ Data pesanan tidak valid.", show_alert=True)
        return

    order_id = int(order_id_str)

    async with UnitOfWork(session_factory) as uow:
        order = await uow.orders.get(order_id)
        if order is None:
            await callback.answer("❌ Pesanan tidak ditemukan.", show_alert=True)
            return

    # If the order is already PAID, confirm to the user
    if order.status == OrderStatus.PAID.value:
        await state.clear()
        await callback.message.answer(
            fmt_payment_check_paid(order.id, order.total_smallest_unit, settings.CURRENCY)
        )
        await callback.answer("✅ Pembayaran sudah diterima!")
        return

    # If the order was cancelled, tell the user
    if order.status == OrderStatus.CANCELLED.value:
        await state.clear()
        await callback.answer("❌ Pesanan telah dibatalkan.", show_alert=True)
        return

    # For Pakasir, query the gateway for status
    async with UnitOfWork(session_factory) as uow:
        payment = await uow.payments.get_pending_by_order(order_id)

    if payment is not None and payment.provider == "pakasir" and payment.payment_identifier:
        payment_svc = PaymentService()
        try:
            detail = await payment_svc.pakasir.get_transaction_detail(
                order_id=payment.payment_identifier,
                amount=payment.final_amount or order.total_smallest_unit,
            )
            if detail.transaction.status in ("completed", "success", "paid"):
                # Mark as paid
                checkout = CheckoutService(session_factory)
                await checkout.confirm_payment(
                    order_id,
                    telegram_charge_id=payment.payment_identifier,
                    provider_charge_id=payment.payment_identifier,
                    provider_name="pakasir",
                )
                await state.clear()
                await callback.message.answer(
                    fmt_payment_check_paid(order.id, order.total_smallest_unit, settings.CURRENCY)
                )
                await callback.answer("✅ Pembayaran diterima!")

                # Notify admins of low stock
                try:
                    from ...features.payments.router import _notify_low_stock
                    await _notify_low_stock(callback.bot, session_factory)
                except Exception:
                    pass

                try:
                    await payment_svc.close()
                except Exception:
                    pass
                return
        except Exception as exc:
            logger.warning("Pakasir status check failed for order %d: %s", order_id, exc)
        finally:
            try:
                await payment_svc.close()
            except Exception:
                pass

    # Payment not yet received
    await callback.answer()
    await callback.message.answer(fmt_payment_check_pending())


@router.callback_query(lambda c: c.data and c.data.startswith("pay:cancel:"))
async def cb_payment_cancel(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Cancel an off-platform (QRIS/Pakasir) payment and release stock."""
    order_id_str = callback.data.split(":")[-1]  # type: ignore[union-attr]
    if not order_id_str or not order_id_str.isdigit():
        await callback.answer("❌ Data pesanan tidak valid.", show_alert=True)
        return

    order_id = int(order_id_str)
    user_id = callback.from_user.id

    async with UnitOfWork(session_factory) as uow:
        order = await uow.orders.get(order_id)
        if order is None:
            await callback.answer("❌ Pesanan tidak ditemukan.", show_alert=True)
            return

    # Can only cancel orders that are still awaiting payment
    if order.status not in (
        OrderStatus.PENDING.value,
        OrderStatus.AWAITING_PAYMENT.value,
    ):
        await callback.answer("❌ Pesanan tidak dapat dibatalkan.", show_alert=True)
        return

    # For Pakasir, attempt to cancel the transaction on the gateway
    async with UnitOfWork(session_factory) as uow:
        payment = await uow.payments.get_pending_by_order(order_id)

    if payment is not None and payment.provider == "pakasir" and payment.payment_identifier:
        payment_svc = PaymentService()
        try:
            await payment_svc.pakasir.cancel_transaction(
                order_id=payment.payment_identifier,
                amount=payment.final_amount or order.total_smallest_unit,
            )
        except Exception as exc:
            logger.warning("Pakasir cancel failed for order %d: %s", order_id, exc)
        finally:
            try:
                await payment_svc.close()
            except Exception:
                pass

    # Cancel order and release stock
    checkout = CheckoutService(session_factory)
    cancelled = await checkout.cancel_order(order_id, user_id)

    if cancelled:
        # Mark any PENDING payment as FAILED so it doesn't linger
        if payment is not None:
            async with UnitOfWork(session_factory) as uow:
                await uow.payments.update_status(payment.id, PaymentStatus.FAILED)

        await state.clear()
        await callback.message.answer(fmt_payment_cancelled(order_id))
        await callback.answer("❌ Dibatalkan.")
    else:
        await callback.answer("❌ Gagal membatalkan pesanan.", show_alert=True)
