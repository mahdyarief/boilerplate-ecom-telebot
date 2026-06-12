"""Orders router — list orders, view detail, cancel order.

Interaction flow:

1. ``/orders``  →  list recent orders with status badges
2. ``ord:<id>`` →  order detail (items, total, status, address)
3. ``ord_cancel:<id>`` →  cancel order (release stock)
4. ``ord_bck:`` →  back to order list

Callback-data schema (all ≤64 bytes):

* ``ord:<order_id>``           — view order detail
* ``ord_cancel:<order_id>``   — cancel order
* ``ord_bck:``                — back to order list
"""

from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command

from ...app.services.checkout import CheckoutService
from ...core.config import settings
from ...core.constants import OrderStatus
from ...infrastructure.persistence.uow import UnitOfWork
from ..checkout.texts import fmt_order_detail, fmt_orders_list

logger = logging.getLogger(__name__)

router = Router(name="orders")

# ── Callback data prefixes ────────────────────────────────

_ORD_PREFIX = "ord:"
_ORD_CANCEL_PREFIX = "ord_cancel:"
_ORD_BACK = "ord_bck:"


# ── Command handler ──────────────────────────────────────


@router.message(Command("orders"))
async def cmd_orders(
    message: types.Message,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Show the user's recent orders."""
    user_id = message.from_user.id

    # Ensure user exists
    async with UnitOfWork(session_factory) as uow:
        await uow.users.get_or_create(user_id)

    async with UnitOfWork(session_factory) as uow:
        orders = await uow.orders.list_by_user(user_id, limit=10)

    if not orders:
        await message.answer("📭 Anda belum memiliki pesanan.\n\nKetik /catalog untuk mulai belanja!")
        return

    text = fmt_orders_list(orders, settings.CURRENCY)

    from ...shared.keyboards import orders_list_kb
    kb = orders_list_kb(orders, currency=settings.CURRENCY)
    await message.answer(text, reply_markup=kb)


# ── Callback: View order detail ──────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith(_ORD_PREFIX))
async def cb_order_detail(
    callback: types.CallbackQuery,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Show order detail — items, total, status, shipping address."""
    assert callback.data is not None
    payload = callback.data[len(_ORD_PREFIX):]

    # Distinguish from ord_cancel and ord_bck
    if not payload.isdigit():
        await callback.answer("❌ Pesanan tidak valid.", show_alert=True)
        return

    order_id = int(payload)
    user_id = callback.from_user.id

    async with UnitOfWork(session_factory) as uow:
        order = await uow.orders.get(order_id)

    if order is None or order.user_id != user_id:
        await callback.answer("❌ Pesanan tidak ditemukan.", show_alert=True)
        return

    async with UnitOfWork(session_factory) as uow:
        items = await uow.order_items.list_by_order(order_id)

    text = fmt_order_detail(
        order_id=order.id,
        status=order.status,
        items=items,
        total_smallest_unit=order.total_smallest_unit,
        currency=settings.CURRENCY,
        shipping_address=order.shipping_address,
    )

    cancellable = order.status in (
        OrderStatus.PENDING.value,
        OrderStatus.AWAITING_PAYMENT.value,
    )

    reorderable = order.status in (
        OrderStatus.PAID.value,
        OrderStatus.SHIPPED.value,
        OrderStatus.DELIVERED.value,
    )

    from ...shared.keyboards import order_detail_kb
    kb = order_detail_kb(order_id, cancellable=cancellable, reorderable=reorderable)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# ── Callback: Cancel order ───────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith(_ORD_CANCEL_PREFIX))
async def cb_order_cancel(
    callback: types.CallbackQuery,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Cancel an order and release reserved stock."""
    assert callback.data is not None
    payload = callback.data[len(_ORD_CANCEL_PREFIX):]
    if not payload.isdigit():
        await callback.answer("❌ Pesanan tidak valid.", show_alert=True)
        return

    order_id = int(payload)
    user_id = callback.from_user.id

    checkout = CheckoutService(session_factory)
    cancelled = await checkout.cancel_order(order_id, user_id)

    if not cancelled:
        await callback.answer(
            "❌ Pesanan tidak dapat dibatalkan (sudah dibayar atau bukan milik Anda).",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        f"❌ Pesanan #{order_id} telah dibatalkan.\n"
        "Stok telah dikembalikan."
    )
    await callback.answer("❌ Pesanan dibatalkan.")


# ── Callback: Back to orders list ────────────────────────


@router.callback_query(lambda c: c.data == _ORD_BACK)
async def cb_orders_back(
    callback: types.CallbackQuery,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Navigate back to the orders list."""
    user_id = callback.from_user.id

    async with UnitOfWork(session_factory) as uow:
        orders = await uow.orders.list_by_user(user_id, limit=10)

    if not orders:
        try:
            await callback.message.edit_text("📭 Anda belum memiliki pesanan.")
        except Exception:
            await callback.message.answer("📭 Anda belum memiliki pesanan.")
        await callback.answer()
        return

    text = fmt_orders_list(orders, settings.CURRENCY)

    from ...shared.keyboards import orders_list_kb
    kb = orders_list_kb(orders, currency=settings.CURRENCY)
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# ── Callback: Re-order ──────────────────────────────────

_ORD_REORDER_PREFIX = "ord_reorder:"


@router.callback_query(lambda c: c.data and c.data.startswith(_ORD_REORDER_PREFIX))
async def cb_order_reorder(
    callback: types.CallbackQuery,
    session_factory,  # type: ignore[valid-type]
) -> None:
    """Re-order: add all items from a previous order back to the cart.

    Only works for PAID / SHIPPED / DELIVERED orders.  Items whose
    products are no longer active or out of stock are silently skipped,
    and the user is informed.
    """
    assert callback.data is not None
    payload = callback.data[len(_ORD_REORDER_PREFIX):]
    if not payload.isdigit():
        await callback.answer("❌ Pesanan tidak valid.", show_alert=True)
        return

    order_id = int(payload)
    user_id = callback.from_user.id

    async with UnitOfWork(session_factory) as uow:
        order = await uow.orders.get(order_id)
        if order is None or order.user_id != user_id:
            await callback.answer("❌ Pesanan tidak ditemukan.", show_alert=True)
            return

        items = await uow.order_items.list_by_order(order_id)

        # Ensure user exists
        await uow.users.get_or_create(user_id)
        await uow.session.flush()

        added = 0
        skipped = 0

        for item in items:
            product = await uow.products.get(item.product_id)
            if product is None or not product.is_active:
                skipped += 1
                continue
            if product.stock <= 0:
                skipped += 1
                continue

            # Check current cart quantity against stock
            existing = await uow.cart_items.find_by_user_and_product(user_id, item.product_id)
            current_qty = existing.quantity if existing else 0
            if current_qty + item.quantity > product.stock:
                # Add only up to stock
                available_qty = product.stock - current_qty
                if available_qty > 0:
                    await uow.cart_items.add_item(
                        user_id=user_id,
                        product_id=item.product_id,
                        quantity=available_qty,
                    )
                    added += 1
                else:
                    skipped += 1
            else:
                await uow.cart_items.add_item(
                    user_id=user_id,
                    product_id=item.product_id,
                    quantity=item.quantity,
                )
                added += 1

    if added > 0 and skipped > 0:
        await callback.answer(
            f"✅ {added} produk ditambahkan, {skipped} tidak tersedia.",
            show_alert=True,
        )
    elif added > 0:
        await callback.answer(f"✅ {added} produk ditambahkan ke keranjang!", show_alert=True)
    else:
        await callback.answer("❌ Tidak ada produk yang dapat ditambahkan.", show_alert=True)
