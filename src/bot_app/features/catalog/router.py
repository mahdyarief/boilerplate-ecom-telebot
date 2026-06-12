"""Catalog router — browse categories → products → product detail.

Interaction flow (all via inline keyboards):

1. ``/catalog``  →  root category list
2. Tap a category  →  subcategories (if any) + products in this category
3. Tap a product  →  product detail with "Add to Cart" button
4. "Add to Cart"  →  adds to cart, stays on product detail
5. Navigation: "Back" returns to the previous level, "Home" to categories

Callback-data schema (all ≤64 bytes):

* ``cat:<id>``         — select category
* ``prd:<id>``         — select product
* ``add:<id>``         — add product to cart
* ``bck:cat:<id>``     — back to category view
* ``bck:root``         — back to root categories
"""

from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command

from ...core.config import settings
from ...infrastructure.persistence.uow import UnitOfWork
from ...shared.money import Money
from .texts import fmt_product_detail, fmt_products_list

logger = logging.getLogger(__name__)

router = Router(name="catalog")

# ── Callback data helpers ─────────────────────────────────

_CAT_PREFIX = "cat:"
_PRD_PREFIX = "prd:"
_ADD_PREFIX = "add:"
_BACK_CAT_PREFIX = "bck:cat:"
_BACK_ROOT = "bck:root"


def _parse_callback(data: str) -> tuple[str, str | None]:
    """Return (action, payload) from callback data."""
    if data.startswith(_CAT_PREFIX):
        return "cat", data[len(_CAT_PREFIX):]
    if data.startswith(_PRD_PREFIX):
        return "prd", data[len(_PRD_PREFIX):]
    if data.startswith(_ADD_PREFIX):
        return "add", data[len(_ADD_PREFIX):]
    if data.startswith(_BACK_CAT_PREFIX):
        return "bck_cat", data[len(_BACK_CAT_PREFIX):]
    if data == _BACK_ROOT:
        return "bck_root", None
    return "unknown", None


async def _build_category_view(
    category_id: int,
    session_factory,
) -> tuple[str, types.InlineKeyboardMarkup]:
    """Shared helper: build the (text, keyboard) pair for a category page."""
    async with UnitOfWork(session_factory) as uow:
        category = await uow.categories.get(category_id)
        subcategories = await uow.categories.list_active(parent_id=category_id)
        products = await uow.products.list_by_category(category_id, active_only=True)

    assert category is not None  # caller should have validated

    # Build text
    title = f"📂 {category.name}\n\n"
    if products:
        product_text = fmt_products_list(products, settings.CURRENCY)
        text = title + product_text
    else:
        text = title + "📭 Tidak ada produk di kategori ini."

    # Build keyboard
    buttons: list[list[types.InlineKeyboardButton]] = []

    for p in products:
        buttons.append(
            [types.InlineKeyboardButton(text=f"📦 {p.name}", callback_data=f"{_PRD_PREFIX}{p.id}")]
        )
    for sc in subcategories:
        buttons.append(
            [types.InlineKeyboardButton(text=f"📂 {sc.name}", callback_data=f"{_CAT_PREFIX}{sc.id}")]
        )
    if category.parent_id is not None:
        buttons.append(
            [types.InlineKeyboardButton(
                text="⬅️ Kembali",
                callback_data=f"{_BACK_CAT_PREFIX}{category.parent_id}",
            )]
        )
    buttons.append(
        [types.InlineKeyboardButton(text="🏠 Katalog", callback_data=_BACK_ROOT)]
    )

    return text, types.InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Command handler ───────────────────────────────────────


@router.message(Command("catalog"))
async def cmd_catalog(message: types.Message, session_factory) -> None:  # type: ignore[valid-type]
    """Show the root list of active categories."""
    async with UnitOfWork(session_factory) as uow:
        categories = await uow.categories.list_active()

    if not categories:
        await message.answer("📭 Katalog kosong — belum ada kategori.")
        return

    from ...shared.keyboards import categories_kb

    kb = categories_kb(categories)
    await message.answer("🛍️ Pilih kategori:", reply_markup=kb)


# ── Callback query handlers ───────────────────────────────


@router.callback_query(lambda c: _parse_callback(c.data)[0] == "cat")
async def cb_category(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Category selected — show subcategories + products inside."""
    _, payload = _parse_callback(callback.data)
    if payload is None or not payload.isdigit():
        await callback.answer("❌ Kategori tidak valid.", show_alert=True)
        return

    category_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        category = await uow.categories.get(category_id)
    if category is None or not category.is_active:
        await callback.answer("❌ Kategori tidak ditemukan.", show_alert=True)
        return

    text, kb = await _build_category_view(category_id, session_factory)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: _parse_callback(c.data)[0] == "prd")
async def cb_product(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Product selected — show detail with photo (if available) and Add-to-Cart button."""
    _, payload = _parse_callback(callback.data)
    if payload is None or not payload.isdigit():
        await callback.answer("❌ Produk tidak valid.", show_alert=True)
        return

    product_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        product = await uow.products.get(product_id)
        if product is None or not product.is_active:
            await callback.answer("❌ Produk tidak ditemukan.", show_alert=True)
            return

        # Check for product images
        cover_image = await uow.product_images.get_cover(product_id)

    price = Money(product.price_smallest_unit, settings.CURRENCY)
    text = fmt_product_detail(
        product.name,
        price,
        product.stock,
        product.description,
    )

    from ...shared.keyboards import product_detail_kb

    kb = product_detail_kb(product_id, product.category_id)

    if cover_image is not None:
        # Send photo with caption and inline keyboard
        try:
            await callback.message.answer_photo(
                photo=cover_image.file_id,
                caption=text,
                reply_markup=kb,
            )
        except Exception:
            # Fallback to text if photo fails
            try:
                await callback.message.edit_text(text, reply_markup=kb)
            except Exception:
                await callback.message.answer(text, reply_markup=kb)
    else:
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: _parse_callback(c.data)[0] == "add")
async def cb_add_to_cart(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Add product to cart (or increment if already present)."""
    _, payload = _parse_callback(callback.data)
    if payload is None or not payload.isdigit():
        await callback.answer("❌ Produk tidak valid.", show_alert=True)
        return

    product_id = int(payload)
    user_id = callback.from_user.id

    async with UnitOfWork(session_factory) as uow:
        product = await uow.products.get(product_id)
        if product is None or not product.is_active:
            await callback.answer("❌ Produk tidak ditemukan.", show_alert=True)
            return
        if product.stock <= 0:
            await callback.answer("⚠️ Stok habis!", show_alert=True)
            return

        # Ensure user exists
        await uow.users.get_or_create(user_id)
        await uow.session.flush()

        # Check current cart quantity against stock
        existing = await uow.cart_items.find_by_user_and_product(user_id, product_id)
        current_qty = existing.quantity if existing else 0
        if current_qty >= product.stock:
            await callback.answer("⚠️ Stok tidak cukup!", show_alert=True)
            return

        await uow.cart_items.add_item(
            user_id=user_id,
            product_id=product_id,
            quantity=1,
        )

    await callback.answer(f"✅ {product.name} ditambahkan ke keranjang!")


@router.callback_query(lambda c: _parse_callback(c.data)[0] == "bck_root")
async def cb_back_root(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Navigate back to the root category list."""
    async with UnitOfWork(session_factory) as uow:
        categories = await uow.categories.list_active()

    if not categories:
        try:
            await callback.message.edit_text("📭 Katalog kosong.")
        except Exception:
            await callback.message.answer("📭 Katalog kosong.")
        await callback.answer()
        return

    from ...shared.keyboards import categories_kb

    kb = categories_kb(categories)
    try:
        await callback.message.edit_text("🛍️ Pilih kategori:", reply_markup=kb)
    except Exception:
        await callback.message.answer("🛍️ Pilih kategori:", reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: _parse_callback(c.data)[0] == "bck_cat")
async def cb_back_category(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Navigate back to a specific category view."""
    _, payload = _parse_callback(callback.data)
    if payload is None or not payload.isdigit():
        await callback.answer("❌ Kategori tidak valid.", show_alert=True)
        return

    category_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        category = await uow.categories.get(category_id)
    if category is None or not category.is_active:
        await callback.answer("❌ Kategori tidak ditemukan.", show_alert=True)
        return

    text, kb = await _build_category_view(category_id, session_factory)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()
