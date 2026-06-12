"""Checkout router — FSM-driven checkout flow: address → review → pay.

Interaction flow (all via inline keyboards + FSM):

1. ``/checkout`` or ``cko:start``  →  ask shipping address (FSM: address)
2. User types address  →  show review (FSM: review)
3. ``cko:confirm``  →  reserve stock, create order, send invoice (FSM: paying)
4. ``cko:cancel``  →  cancel, return to cart

Payment lifecycle (handled in ``features/payments/router.py``):

5. ``pre_checkout_query``  →  verify stock & order status
6. ``successful_payment``  →  mark order as paid, confirm

Callback-data schema (all ≤64 bytes):

* ``cko:start``    — start checkout
* ``cko:confirm``  — confirm and pay
* ``cko:cancel``   — cancel checkout
"""

from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from ...app.services.checkout import CheckoutService
from ...app.services.discount import DiscountService
from ...app.services.pricing import LineItem, compute_total
from ...core.config import settings
from ...core.constants import OrderStatus
from ...core.errors import CouponError, NotFoundError, StockError
from ...infrastructure.persistence.uow import UnitOfWork
from .states import CheckoutStates
from .texts import (
    fmt_checkout_coupon_prompt,
    fmt_coupon_applied,
    fmt_coupon_invalid,
    fmt_review_with_coupon,
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
    from ...shared.keyboards import checkout_confirm_kb
    from ...shared.money import Money

    line_items: list[LineItem] = []
    lines: list[str] = []
    cart_items_data: list[tuple[str, int, int]] = []  # (name, qty, unit_price)

    async with UnitOfWork(session_factory) as uow:
        cart_items = await uow.cart_items.list_by_user(user_id)
        for item in cart_items:
            product = await uow.products.get(item.product_id)
            if product is None:
                continue
            unit_price = Money(product.price_smallest_unit, currency)
            subtotal = unit_price * item.quantity
            lines.append(f"  • {product.name} x{item.quantity} — {subtotal.format()}")
            line_items.append(LineItem(unit_price=unit_price, quantity=item.quantity))
            cart_items_data.append((product.name, item.quantity, product.price_smallest_unit))

    breakdown = compute_total(line_items, currency, coupon_percent=coupon_percent)
    discount_amount = breakdown.discount.amount_minor

    total = breakdown.total

    review_text = fmt_review_with_coupon(
        items=[],  # We build lines manually
        total_smallest_unit=total.amount_minor,
        currency=currency,
        shipping_address=shipping_address,
        discount_percent=coupon_percent,
        discount_amount=discount_amount,
    )

    # Rebuild review_text with actual cart lines
    parts = review_text.split("📋 **Konfirmasi Pesanan**\n\n", 1)
    cart_lines_text = "\n".join(lines)
    if len(parts) == 2:
        review_text = "📋 **Konfirmasi Pesanan**\n\n" + cart_lines_text + parts[1]

    kb = checkout_confirm_kb()
    return review_text, kb


# ── FSM: Review — Confirm ───────────────────────────────


@router.callback_query(lambda c: c.data == f"{_CHECKOUT_PREFIX}confirm")
async def cb_checkout_confirm(
    callback: types.CallbackQuery,
    state: FSMContext,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Confirm checkout — create order, reserve stock, send invoice."""
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

    # Load order items for the invoice
    async with UnitOfWork(session_factory) as uow:
        order_items = await uow.order_items.list_by_order(order.id)

    # Update order status to AWAITING_PAYMENT
    async with UnitOfWork(session_factory) as uow:
        await uow.orders.update_status(order.id, OrderStatus.AWAITING_PAYMENT)

    # Build and send Telegram invoice
    if not settings.PROVIDER_TOKEN:
        # No provider token configured — mark as paid immediately (dev mode)
        logger.warning("PROVIDER_TOKEN not set — skipping invoice, auto-confirming order %d", order.id)
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
        return

    # Real invoice
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


# ── FSM: Review — Cancel ────────────────────────────────


@router.callback_query(lambda c: c.data == f"{_CHECKOUT_PREFIX}cancel")
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
