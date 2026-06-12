"""Cart router -- view, adjust quantities, remove items, clear cart.

Interaction flow:

1. ``/cart``  ->  list all items with per-item controls (minus/qty/plus + remove)
2. ``qty:<id>:-``  ->  decrement quantity (remove if hits 0)
3. ``qty:<id>:+``  ->  increment quantity (capped by stock)
4. ``rm:<id>``  ->  remove item from cart
5. ``cc:``     ->  prompt to confirm clear
6. ``cc:yes``  ->  clear entire cart
7. ``cc:no``   ->  cancel clear

Callback-data schema:

* ``qty:<cart_item_id>:-``    — decrement
* ``qty:<cart_item_id>:+``    — increment
* ``rm:<cart_item_id>``       — remove item
* ``cc:``                     — start clearing
* ``cc:yes``                  — confirm clear
* ``cc:no``                   — cancel clear
* ``bck:root``                — go to catalog
"""

from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command

from ...core.config import settings
from ...infrastructure.persistence.uow import UnitOfWork
from ...shared.money import Money

logger = logging.getLogger(__name__)

router = Router(name="cart")

# ── Callback data prefixes ────────────────────────────────

_QTY_PREFIX = "qty:"
_RM_PREFIX = "rm:"
_CC_PREFIX = "cc:"
_BACK_ROOT = "bck:root"


# ── Helpers ───────────────────────────────────────────────


async def _build_cart_message(
    user_id: int,
    session_factory,
) -> tuple[str, types.InlineKeyboardMarkup | None]:
    """Build the cart message (text + combined keyboard).

    Returns (text, keyboard).  ``keyboard`` is ``None`` when the cart is empty.
    """
    async with UnitOfWork(session_factory) as uow:
        cart_items = await uow.cart_items.list_by_user(user_id)

    if not cart_items:
        return "🛒 Keranjang Anda kosong.\n\nKetik /catalog untuk mulai belanja!", None

    from ...shared.keyboards import cart_footer_kb, cart_item_kb

    lines: list[str] = []
    item_keyboards: list[types.InlineKeyboardMarkup] = []

    for item in cart_items:
        # Reload product info
        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(item.product_id)
        if product is None:
            continue

        unit_price = Money(product.price_smallest_unit, settings.CURRENCY)
        subtotal = unit_price * item.quantity
        lines.append(f"• {product.name} x{item.quantity} — {subtotal.format()}")
        item_keyboards.append(cart_item_kb(item.id, item.quantity))

    if not lines:
        return "🛒 Keranjang Anda kosong.", None

    total = Money.zero(settings.CURRENCY)
    for item in cart_items:
        async with UnitOfWork(session_factory) as uow:
            product = await uow.products.get(item.product_id)
        if product is None:
            continue
        unit_price = Money(product.price_smallest_unit, settings.CURRENCY)
        total = total + (unit_price * item.quantity)

    text = "🛒 Keranjang Anda:\n\n" + "\n".join(lines) + f"\n\n💰 Total: {total.format()}"

    # Combine per-item buttons + footer into one keyboard
    all_buttons: list[list[types.InlineKeyboardButton]] = []
    for ikb in item_keyboards:
        all_buttons.extend(ikb.inline_keyboard)
    all_buttons.extend(cart_footer_kb().inline_keyboard)

    return text, types.InlineKeyboardMarkup(inline_keyboard=all_buttons)


# ── Command handler ───────────────────────────────────────


@router.message(Command("cart"))
async def cmd_cart(message: types.Message, session_factory) -> None:  # type: ignore[valid-type]
    """Show the user's cart."""
    user_id = message.from_user.id

    # Ensure user exists
    async with UnitOfWork(session_factory) as uow:
        await uow.users.get_or_create(user_id)

    text, kb = await _build_cart_message(user_id, session_factory)
    if kb is not None:
        await message.answer(text, reply_markup=kb)
    else:
        await message.answer(text)


# ── Callback query handlers ───────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith(_QTY_PREFIX))
async def cb_cart_qty(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Adjust quantity: ``qty:<cart_item_id>:+`` or ``qty:<cart_item_id>:-``."""
    assert callback.data is not None
    payload = callback.data[len(_QTY_PREFIX):]  # e.g. "123:+"
    parts = payload.split(":")
    if len(parts) != 2 or parts[1] not in ("+", "-"):
        await callback.answer("❌ Aksi tidak valid.", show_alert=True)
        return

    cart_item_id = int(parts[0])
    direction = parts[1]
    user_id = callback.from_user.id

    async with UnitOfWork(session_factory) as uow:
        cart_item = await uow.cart_items.get(cart_item_id)
        if cart_item is None or cart_item.user_id != user_id:
            await callback.answer("❌ Item tidak ditemukan.", show_alert=True)
            return

        product = await uow.products.get(cart_item.product_id)
        if product is None:
            await callback.answer("❌ Produk tidak ditemukan.", show_alert=True)
            return

        if direction == "+":
            new_qty = cart_item.quantity + 1
            if new_qty > product.stock:
                await callback.answer("⚠️ Stok tidak cukup!", show_alert=True)
                return
            await uow.cart_items.update_quantity(cart_item_id, new_qty)
        else:  # "-"
            new_qty = cart_item.quantity - 1
            if new_qty <= 0:
                await uow.cart_items.remove_item(cart_item_id)
            else:
                await uow.cart_items.update_quantity(cart_item_id, new_qty)

    # Rebuild cart view
    text, kb = await _build_cart_message(user_id, session_factory)
    if kb is not None:
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            await callback.message.answer(text, reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text)
        except Exception:
            await callback.message.answer(text)
    await callback.answer("📝 Jumlah diperbarui.")


@router.callback_query(lambda c: c.data and c.data.startswith(_RM_PREFIX))
async def cb_cart_remove(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Remove a single item from the cart."""
    assert callback.data is not None
    payload = callback.data[len(_RM_PREFIX):]
    if not payload.isdigit():
        await callback.answer("❌ Item tidak valid.", show_alert=True)
        return

    cart_item_id = int(payload)
    user_id = callback.from_user.id

    async with UnitOfWork(session_factory) as uow:
        cart_item = await uow.cart_items.get(cart_item_id)
        if cart_item is None or cart_item.user_id != user_id:
            await callback.answer("❌ Item tidak ditemukan.", show_alert=True)
            return
        product = await uow.products.get(cart_item.product_id)
        product_name = product.name if product else "Produk"
        await uow.cart_items.remove_item(cart_item_id)

    # Rebuild cart view
    text, kb = await _build_cart_message(user_id, session_factory)
    if kb is not None:
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            await callback.message.answer(text, reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text)
        except Exception:
            await callback.message.answer(text)
    await callback.answer(f"🗑️ {product_name} dihapus dari keranjang.")


@router.callback_query(lambda c: c.data == _CC_PREFIX)
async def cb_cart_clear_start(callback: types.CallbackQuery) -> None:  # type: ignore[valid-type]
    """Prompt for confirmation before clearing the cart."""
    from ...shared.keyboards import confirm_clear_kb

    await callback.message.answer(
        "⚠️ Yakin ingin mengosongkan keranjang?",
        reply_markup=confirm_clear_kb(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith(_CC_PREFIX) and c.data != _CC_PREFIX)
async def cb_cart_clear_confirm(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Handle clear-cart confirmation: ``cc:yes`` or ``cc:no``."""
    assert callback.data is not None
    action = callback.data[len(_CC_PREFIX):]  # "yes" or "no"

    if action == "no":
        await callback.message.delete()
        await callback.answer("Dibatalkan.")
        return

    user_id = callback.from_user.id

    async with UnitOfWork(session_factory) as uow:
        await uow.cart_items.clear_cart(user_id)

    await callback.message.delete()
    await callback.message.answer("🧹 Keranjang dikosongkan.")
    await callback.answer("🧹 Keranjang dikosongkan.")


@router.callback_query(lambda c: c.data == _BACK_ROOT)
async def cb_cart_continue(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Continue shopping — go back to catalog root."""
    async with UnitOfWork(session_factory) as uow:
        categories = await uow.categories.list_active()

    if not categories:
        await callback.answer("📭 Katalog kosong.", show_alert=True)
        return

    from ...shared.keyboards import categories_kb

    kb = categories_kb(categories)
    try:
        await callback.message.edit_text("🛍️ Pilih kategori:", reply_markup=kb)
    except Exception:
        await callback.message.answer("🛍️ Pilih kategori:", reply_markup=kb)
    await callback.answer()
