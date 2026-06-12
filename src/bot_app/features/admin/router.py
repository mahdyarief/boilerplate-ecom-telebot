"""Admin router — gated CRUD for categories, products, orders + broadcast.

All handlers are protected by the ``_is_admin`` guard which checks
``settings.admin_ids``.  Non-admins who try to access admin commands
receive a single denial message.

Interaction flow (all via inline keyboards + FSM):

1. ``/admin`` → admin panel landing (4 buttons: cats / prds / ords / bcast)
2. Categories: list → detail → edit / toggle / delete / new (FSM)
3. Products:   list → detail → edit / toggle / delete / new (FSM)
4. Orders:    list → detail → status transitions
5. Broadcast: compose → preview → confirm / cancel

Callback-data schema (all ≤64 bytes):

* ``adm:cats``                    — category list
* ``adm:cat_new``                 — start new-category FSM
* ``adm:cat:<id>``                — category detail
* ``adm:cat_edit:<id>``           — choose field to edit
* ``adm:cat_edit:<id>:<field>``   — pick specific field
* ``adm:cat_tog:<id>``            — toggle active/inactive
* ``adm:cat_del:<id>``            — soft-delete (set inactive)
* ``adm:prds``                    — product list
* ``adm:prd_new``                 — start new-product FSM
* ``adm:prd_ncat:<cat_id>``       — select category for new product
* ``adm:prd:<id>``                — product detail
* ``adm:prd_edit:<id>``           — choose field to edit
* ``adm:prd_edit:<id>:<field>``   — pick specific field
* ``adm:prd_tog:<id>``            — toggle active/inactive
* ``adm:prd_del:<id>``            — soft-delete (set inactive)
* ``adm:ords``                    — order list
* ``adm:ord:<id>``                — order detail
* ``adm:ord_st:<id>:<status>``    — change order status
* ``adm:bcast``                   — start broadcast FSM
* ``adm:bcast_go``                — confirm broadcast
* ``adm:bcast_no``                — cancel broadcast
* ``adm:back``                    — return to admin panel
"""

from __future__ import annotations

import logging
from datetime import UTC

from aiogram import Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext

from ...core.config import settings
from ...core.constants import OrderStatus
from ...infrastructure.persistence.uow import UnitOfWork
from .states import (
    Broadcast,
    CategoryCreate,
    CategoryEdit,
    CouponCreate,
    ProductCreate,
    ProductEdit,
    ProductImageUpload,
)
from .texts import (
    fmt_admin_order_detail,
    fmt_admin_order_list,
    fmt_admin_panel,
    fmt_ask_broadcast_message,
    fmt_ask_category_edit_value,
    fmt_ask_category_name,
    fmt_ask_category_slug,
    fmt_ask_coupon_code,
    fmt_ask_coupon_discount,
    fmt_ask_coupon_expires,
    fmt_ask_coupon_max_uses,
    fmt_ask_product_description,
    fmt_ask_product_edit_value,
    fmt_ask_product_name,
    fmt_ask_product_price,
    fmt_ask_product_stock,
    fmt_ask_select_category,
    fmt_broadcast_cancelled,
    fmt_broadcast_preview,
    fmt_broadcast_sent,
    fmt_category_created,
    fmt_category_detail,
    fmt_category_list,
    fmt_category_updated,
    fmt_coupon_created,
    fmt_coupon_detail,
    fmt_coupon_list,
    fmt_not_admin,
    fmt_order_status_updated,
    fmt_product_created,
    fmt_product_detail,
    fmt_product_image_added,
    fmt_product_image_cover_set,
    fmt_product_image_deleted,
    fmt_product_images,
    fmt_product_list,
    fmt_product_updated,
)

logger = logging.getLogger(__name__)

router = Router(name="admin")


# ── Admin guard ──────────────────────────────────────────


def _is_admin(user_id: int) -> bool:
    """Return ``True`` if *user_id* is in ``settings.admin_ids``."""
    return user_id in settings.admin_ids


# ── Command: /admin ─────────────────────────────────────


@router.message(Command("admin"))
async def cmd_admin(message: types.Message) -> None:
    """Open the admin panel."""
    if not _is_admin(message.from_user.id):
        await message.answer(fmt_not_admin())
        return

    from ...shared.keyboards import admin_panel_kb
    await message.answer(fmt_admin_panel(), reply_markup=admin_panel_kb())


# ── Admin panel back ─────────────────────────────────────


@router.callback_query(lambda c: c.data == "adm:back")
async def cb_admin_back(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Return to admin panel landing from any admin sub-page."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    # Clear any in-flight FSM state
    await state.clear()

    from ...shared.keyboards import admin_panel_kb
    try:
        await callback.message.edit_text(fmt_admin_panel(), reply_markup=admin_panel_kb())
    except Exception:
        await callback.message.answer(fmt_admin_panel(), reply_markup=admin_panel_kb())
    await callback.answer()


# ══════════════════════════════════════════════════════════
#  CATEGORY MANAGEMENT
# ══════════════════════════════════════════════════════════


@router.callback_query(lambda c: c.data == "adm:cats")
async def cb_admin_cats(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Show the admin category list (including inactive ones)."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    async with UnitOfWork(session_factory) as uow:
        # Get all categories (including inactive) at root level
        from sqlalchemy import select

        from ...infrastructure.persistence.models import Category
        stmt = select(Category).order_by(Category.position, Category.id)
        result = await uow.session.execute(stmt)
        categories = list(result.scalars().all())

    text = fmt_category_list(categories, include_inactive=True)

    from ...shared.keyboards import admin_category_list_kb
    kb = admin_category_list_kb(categories, include_inactive=True)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("adm:cat:") and not c.data.startswith("adm:cat_new") and not c.data.startswith("adm:cat_edit") and not c.data.startswith("adm:cat_tog") and not c.data.startswith("adm:cat_del"))
async def cb_admin_cat_detail(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Show category detail for admin management."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:cat:"):]
    if not payload.isdigit():
        await callback.answer("❌ Kategori tidak valid.", show_alert=True)
        return

    category_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        category = await uow.categories.get(category_id)

    if category is None:
        await callback.answer("❌ Kategori tidak ditemukan.", show_alert=True)
        return

    text = fmt_category_detail(category)

    from ...shared.keyboards import admin_category_detail_kb
    kb = admin_category_detail_kb(category_id, is_active=category.is_active)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# ── Category: Create (FSM) ──────────────────────────────


@router.callback_query(lambda c: c.data == "adm:cat_new")
async def cb_admin_cat_new(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start new-category FSM → ask for name."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    await state.set_state(CategoryCreate.name)
    await callback.message.answer(fmt_ask_category_name())
    await callback.answer()


@router.message(StateFilter(CategoryCreate.name))
async def process_cat_new_name(message: types.Message, state: FSMContext) -> None:
    """Receive new category name → ask for slug."""
    if not message.text:
        await message.answer("⚠️ Ketik nama kategori sebagai teks.")
        return

    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Nama terlalu pendek (min 2 karakter).")
        return

    await state.update_data(cat_name=name)
    await state.set_state(CategoryCreate.slug)
    await message.answer(fmt_ask_category_slug())


@router.message(StateFilter(CategoryCreate.slug))
async def process_cat_new_slug(message: types.Message, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Receive new category slug → create the category."""
    if not message.text:
        await state.clear()
        await message.answer("⚠️ Ketik slug kategori sebagai teks.")
        return

    slug = message.text.strip().lower().replace(" ", "-")
    data = await state.get_data()
    name = data.get("cat_name", "")

    async with UnitOfWork(session_factory) as uow:
        # Check slug uniqueness
        existing = await uow.categories.get_by_slug(slug)
        if existing is not None:
            await message.answer(
                f"⚠️ Slug '{slug}' sudah digunakan. Ketik slug lain:"
            )
            return  # Stay in the same state so admin can retry

        category = await uow.categories.create(name=name, slug=slug)

    await state.clear()
    await message.answer(fmt_category_created(category))


# ── Category: Edit (FSM) ────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("adm:cat_edit:") and ":" not in c.data[len("adm:cat_edit:"):])
async def cb_admin_cat_edit(callback: types.CallbackQuery, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Show category edit field picker."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:cat_edit:"):]
    if not payload.isdigit():
        await callback.answer("❌ Kategori tidak valid.", show_alert=True)
        return

    category_id = int(payload)
    await state.update_data(edit_cat_id=category_id)

    from ...shared.keyboards import admin_category_edit_field_kb
    kb = admin_category_edit_field_kb(category_id)

    try:
        await callback.message.edit_text("✏️ Pilih field yang ingin diubah:", reply_markup=kb)
    except Exception:
        await callback.message.answer("✏️ Pilih field yang ingin diubah:", reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("adm:cat_edit:") and ":" in c.data[len("adm:cat_edit:"):])
async def cb_admin_cat_edit_field(callback: types.CallbackQuery, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Admin picked a field to edit → ask for the new value."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    # data format: adm:cat_edit:<id>:<field>
    parts = callback.data[len("adm:cat_edit:"):].split(":")
    if len(parts) != 2 or not parts[0].isdigit():
        await callback.answer("❌ Format tidak valid.", show_alert=True)
        return

    category_id = int(parts[0])
    field = parts[1]

    async with UnitOfWork(session_factory) as uow:
        category = await uow.categories.get(category_id)
    if category is None:
        await callback.answer("❌ Kategori tidak ditemukan.", show_alert=True)
        return

    # Get current value for the field
    current_values = {
        "name": category.name,
        "slug": category.slug,
        "position": str(category.position),
    }
    current = current_values.get(field, "—")

    await state.update_data(edit_cat_id=category_id, edit_cat_field=field)
    await state.set_state(CategoryEdit.value)
    await callback.message.answer(fmt_ask_category_edit_value(field, current))
    await callback.answer()


@router.message(StateFilter(CategoryEdit.value))
async def process_cat_edit_value(message: types.Message, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Receive new value for category field → update the category."""
    if not message.text:
        await message.answer("⚠️ Ketik nilai baru sebagai teks.")
        return

    data = await state.get_data()
    category_id = data.get("edit_cat_id")
    field = data.get("edit_cat_field")

    if category_id is None or field is None:
        await state.clear()
        await message.answer("❌ Sesi edit kadaluarsa. Silakan coba lagi.")
        return

    value = message.text.strip()

    async with UnitOfWork(session_factory) as uow:
        category = await uow.categories.get(category_id)
        if category is None:
            await state.clear()
            await message.answer("❌ Kategori tidak ditemukan.")
            return

        if field == "name":
            await uow.categories.update(category_id, name=value)
        elif field == "slug":
            existing = await uow.categories.get_by_slug(value)
            if existing is not None:
                await message.answer(f"⚠️ Slug '{value}' sudah digunakan. Ketik slug lain:")
                return  # Stay in state for retry
            await uow.categories.update(category_id, slug=value)
        elif field == "position":
            try:
                pos = int(value)
            except ValueError:
                await message.answer("⚠️ Posisi harus berupa angka. Ketik lagi:")
                return
            await uow.categories.update(category_id, position=pos)

    await state.clear()
    await message.answer(fmt_category_updated(category))


# ── Category: Toggle ────────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("adm:cat_tog:"))
async def cb_admin_cat_toggle(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Toggle category active/inactive."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:cat_tog:"):]
    if not payload.isdigit():
        await callback.answer("❌ Kategori tidak valid.", show_alert=True)
        return

    category_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        category = await uow.categories.get(category_id)
        if category is None:
            await callback.answer("❌ Kategori tidak ditemukan.", show_alert=True)
            return
        new_active = not category.is_active
        await uow.categories.toggle_active(category_id, is_active=new_active)

    status = "diaktifkan" if new_active else "dinonaktifkan"
    await callback.answer(f"✅ Kategori {status}.")
    # Re-show detail
    await cb_admin_cat_detail(callback, session_factory)


# ── Category: Delete (soft) ─────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("adm:cat_del:"))
async def cb_admin_cat_delete(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Soft-delete a category (set is_active=False)."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:cat_del:"):]
    if not payload.isdigit():
        await callback.answer("❌ Kategori tidak valid.", show_alert=True)
        return

    category_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        category = await uow.categories.get(category_id)
        if category is None:
            await callback.answer("❌ Kategori tidak ditemukan.", show_alert=True)
            return
        await uow.categories.toggle_active(category_id, is_active=False)

    await callback.answer("🗑️ Kategori dinonaktifkan.")
    # Re-show detail
    await cb_admin_cat_detail(callback, session_factory)


# ══════════════════════════════════════════════════════════
#  PRODUCT MANAGEMENT
# ══════════════════════════════════════════════════════════


@router.callback_query(lambda c: c.data == "adm:prds")
async def cb_admin_prds(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Show the admin product list (including inactive ones)."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    async with UnitOfWork(session_factory) as uow:
        from sqlalchemy import select

        from ...infrastructure.persistence.models import Product
        stmt = select(Product).order_by(Product.id)
        result = await uow.session.execute(stmt)
        products = list(result.scalars().all())

    text = fmt_product_list(products, currency=settings.CURRENCY)

    from ...shared.keyboards import admin_product_list_kb
    kb = admin_product_list_kb(products, include_inactive=True)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("adm:prd:") and not c.data.startswith("adm:prd_new") and not c.data.startswith("adm:prd_edit") and not c.data.startswith("adm:prd_tog") and not c.data.startswith("adm:prd_del") and not c.data.startswith("adm:prd_ncat"))
async def cb_admin_prd_detail(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Show product detail for admin management."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:prd:"):]
    if not payload.isdigit():
        await callback.answer("❌ Produk tidak valid.", show_alert=True)
        return

    product_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        product = await uow.products.get(product_id)

    if product is None:
        await callback.answer("❌ Produk tidak ditemukan.", show_alert=True)
        return

    text = fmt_product_detail(product, currency=settings.CURRENCY)

    from ...shared.keyboards import admin_product_detail_kb
    kb = admin_product_detail_kb(product_id, is_active=product.is_active)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# ── Product: Create (FSM) ───────────────────────────────


@router.callback_query(lambda c: c.data == "adm:prd_new")
async def cb_admin_prd_new(callback: types.CallbackQuery, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Start new-product FSM → ask for category selection."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    async with UnitOfWork(session_factory) as uow:
        categories = await uow.categories.list_active()

    if not categories:
        await callback.answer("⚠️ Tidak ada kategori aktif. Buat kategori dulu.", show_alert=True)
        return

    from ...shared.keyboards import admin_product_new_category_kb
    kb = admin_product_new_category_kb(categories)

    await state.set_state(ProductCreate.category)
    try:
        await callback.message.edit_text(fmt_ask_select_category(), reply_markup=kb)
    except Exception:
        await callback.message.answer(fmt_ask_select_category(), reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("adm:prd_ncat:"))
async def cb_admin_prd_new_cat(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Admin selected a category for the new product → ask for name."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:prd_ncat:"):]
    if not payload.isdigit():
        await callback.answer("❌ Kategori tidak valid.", show_alert=True)
        return

    category_id = int(payload)
    await state.update_data(new_prd_cat_id=category_id)
    await state.set_state(ProductCreate.name)
    await callback.message.answer(fmt_ask_product_name())
    await callback.answer()


@router.message(StateFilter(ProductCreate.name))
async def process_prd_new_name(message: types.Message, state: FSMContext) -> None:
    """Receive new product name → ask for price."""
    if not message.text:
        await message.answer("⚠️ Ketik nama produk sebagai teks.")
        return

    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Nama terlalu pendek (min 2 karakter).")
        return

    await state.update_data(new_prd_name=name)
    await state.set_state(ProductCreate.price)
    await message.answer(fmt_ask_product_price())


@router.message(StateFilter(ProductCreate.price))
async def process_prd_new_price(message: types.Message, state: FSMContext) -> None:
    """Receive new product price → ask for stock."""
    if not message.text:
        await message.answer("⚠️ Ketik harga sebagai angka.")
        return

    try:
        price = int(message.text.strip().replace(".", "").replace(",", ""))
    except ValueError:
        await message.answer("⚠️ Harga tidak valid. Ketik angka saja (contoh: 50000):")
        return

    if price < 0:
        await message.answer("⚠️ Harga tidak boleh negatif.")
        return

    await state.update_data(new_prd_price=price)
    await state.set_state(ProductCreate.stock)
    await message.answer(fmt_ask_product_stock())


@router.message(StateFilter(ProductCreate.stock))
async def process_prd_new_stock(message: types.Message, state: FSMContext) -> None:
    """Receive new product stock → ask for description."""
    if not message.text:
        await message.answer("⚠️ Ketik stok sebagai angka.")
        return

    try:
        stock = int(message.text.strip())
    except ValueError:
        await message.answer("⚠️ Stok tidak valid. Ketik angka saja:")
        return

    if stock < 0:
        await message.answer("⚠️ Stok tidak boleh negatif.")
        return

    await state.update_data(new_prd_stock=stock)
    await state.set_state(ProductCreate.description)
    await message.answer(fmt_ask_product_description())


@router.message(StateFilter(ProductCreate.description))
async def process_prd_new_description(message: types.Message, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Receive new product description → create the product."""
    description = None
    if message.text and message.text.strip() != "/skip":
        description = message.text.strip()

    data = await state.get_data()
    category_id = data.get("new_prd_cat_id")
    name = data.get("new_prd_name", "")
    price = data.get("new_prd_price", 0)
    stock = data.get("new_prd_stock", 0)

    if category_id is None:
        await state.clear()
        await message.answer("❌ Sesi pembuatan produk kadaluarsa. Silakan coba lagi.")
        return

    async with UnitOfWork(session_factory) as uow:
        product = await uow.products.create(
            category_id=category_id,
            name=name,
            price_smallest_unit=price,
            description=description,
            stock=stock,
        )

    await state.clear()
    await message.answer(fmt_product_created(product, currency=settings.CURRENCY))


# ── Product: Edit (FSM) ────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("adm:prd_edit:") and ":" not in c.data[len("adm:prd_edit:"):])
async def cb_admin_prd_edit(callback: types.CallbackQuery, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Show product edit field picker."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:prd_edit:"):]
    if not payload.isdigit():
        await callback.answer("❌ Produk tidak valid.", show_alert=True)
        return

    product_id = int(payload)
    await state.update_data(edit_prd_id=product_id)

    from ...shared.keyboards import admin_product_edit_field_kb
    kb = admin_product_edit_field_kb(product_id)

    try:
        await callback.message.edit_text("✏️ Pilih field yang ingin diubah:", reply_markup=kb)
    except Exception:
        await callback.message.answer("✏️ Pilih field yang ingin diubah:", reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("adm:prd_edit:") and ":" in c.data[len("adm:prd_edit:"):])
async def cb_admin_prd_edit_field(callback: types.CallbackQuery, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Admin picked a product field to edit → ask for the new value."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    # data format: adm:prd_edit:<id>:<field>
    parts = callback.data[len("adm:prd_edit:"):].split(":")
    if len(parts) != 2 or not parts[0].isdigit():
        await callback.answer("❌ Format tidak valid.", show_alert=True)
        return

    product_id = int(parts[0])
    field = parts[1]

    async with UnitOfWork(session_factory) as uow:
        product = await uow.products.get(product_id)
    if product is None:
        await callback.answer("❌ Produk tidak ditemukan.", show_alert=True)
        return

    # Get current value for the field
    from ...shared.money import Money
    current_values = {
        "name": product.name,
        "description": product.description or "—",
        "price": Money(product.price_smallest_unit, settings.CURRENCY).format(),
        "stock": str(product.stock),
    }
    current = current_values.get(field, "—")

    await state.update_data(edit_prd_id=product_id, edit_prd_field=field)
    await state.set_state(ProductEdit.value)
    await callback.message.answer(fmt_ask_product_edit_value(field, current))
    await callback.answer()


@router.message(StateFilter(ProductEdit.value))
async def process_prd_edit_value(message: types.Message, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Receive new value for product field → update the product."""
    if not message.text:
        await message.answer("⚠️ Ketik nilai baru sebagai teks.")
        return

    data = await state.get_data()
    product_id = data.get("edit_prd_id")
    field = data.get("edit_prd_field")

    if product_id is None or field is None:
        await state.clear()
        await message.answer("❌ Sesi edit kadaluarsa. Silakan coba lagi.")
        return

    value = message.text.strip()

    async with UnitOfWork(session_factory) as uow:
        product = await uow.products.get(product_id)
        if product is None:
            await state.clear()
            await message.answer("❌ Produk tidak ditemukan.")
            return

        if field == "name":
            await uow.products.update(product_id, name=value)
        elif field == "description":
            desc = value if value != "/skip" else None
            await uow.products.update(product_id, description=desc)
        elif field == "price":
            try:
                price = int(value.replace(".", "").replace(",", ""))
            except ValueError:
                await message.answer("⚠️ Harga tidak valid. Ketik angka saja:")
                return
            if price < 0:
                await message.answer("⚠️ Harga tidak boleh negatif.")
                return
            await uow.products.update(product_id, price_smallest_unit=price)
        elif field == "stock":
            try:
                stock = int(value)
            except ValueError:
                await message.answer("⚠️ Stok tidak valid. Ketik angka saja:")
                return
            if stock < 0:
                await message.answer("⚠️ Stok tidak boleh negatif.")
                return
            await uow.products.update(product_id, stock=stock)

    await state.clear()
    await message.answer(fmt_product_updated(product))


# ── Product: Toggle ────────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("adm:prd_tog:"))
async def cb_admin_prd_toggle(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Toggle product active/inactive."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:prd_tog:"):]
    if not payload.isdigit():
        await callback.answer("❌ Produk tidak valid.", show_alert=True)
        return

    product_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        product = await uow.products.get(product_id)
        if product is None:
            await callback.answer("❌ Produk tidak ditemukan.", show_alert=True)
            return
        new_active = not product.is_active
        await uow.products.toggle_active(product_id, is_active=new_active)

    status = "diaktifkan" if new_active else "dinonaktifkan"
    await callback.answer(f"✅ Produk {status}.")
    # Re-show detail
    await cb_admin_prd_detail(callback, session_factory)


# ── Product: Delete (soft) ─────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("adm:prd_del:"))
async def cb_admin_prd_delete(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Soft-delete a product (set is_active=False)."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:prd_del:"):]
    if not payload.isdigit():
        await callback.answer("❌ Produk tidak valid.", show_alert=True)
        return

    product_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        product = await uow.products.get(product_id)
        if product is None:
            await callback.answer("❌ Produk tidak ditemukan.", show_alert=True)
            return
        await uow.products.toggle_active(product_id, is_active=False)

    await callback.answer("🗑️ Produk dinonaktifkan.")
    # Re-show detail
    await cb_admin_prd_detail(callback, session_factory)


# ══════════════════════════════════════════════════════════
#  ORDER MANAGEMENT
# ══════════════════════════════════════════════════════════


@router.callback_query(lambda c: c.data == "adm:ords")
async def cb_admin_ords(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Show the admin order list (most recent first)."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    async with UnitOfWork(session_factory) as uow:
        from sqlalchemy import select

        from ...infrastructure.persistence.models import Order
        stmt = select(Order).order_by(Order.id.desc()).limit(20)
        result = await uow.session.execute(stmt)
        orders = list(result.scalars().all())

    text = fmt_admin_order_list(orders, currency=settings.CURRENCY)

    from ...shared.keyboards import admin_order_list_kb
    kb = admin_order_list_kb(orders, currency=settings.CURRENCY)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("adm:ord:") and not c.data.startswith("adm:ord_st:"))
async def cb_admin_ord_detail(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Show order detail for admin management with status-transition buttons."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:ord:"):]
    if not payload.isdigit():
        await callback.answer("❌ Pesanan tidak valid.", show_alert=True)
        return

    order_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        order = await uow.orders.get(order_id)
        if order is None:
            await callback.answer("❌ Pesanan tidak ditemukan.", show_alert=True)
            return
        items = await uow.order_items.list_by_order(order_id)

    text = fmt_admin_order_detail(order, items, currency=settings.CURRENCY)

    from ...shared.keyboards import admin_order_detail_kb
    kb = admin_order_detail_kb(order_id, order.status)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("adm:ord_st:"))
async def cb_admin_ord_status(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Change order status."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    # data format: adm:ord_st:<order_id>:<new_status>
    parts = callback.data[len("adm:ord_st:"):].split(":")
    if len(parts) != 2 or not parts[0].isdigit():
        await callback.answer("❌ Format tidak valid.", show_alert=True)
        return

    order_id = int(parts[0])
    new_status_str = parts[1]

    # Validate the new status
    try:
        new_status = OrderStatus(new_status_str)
    except ValueError:
        await callback.answer("❌ Status tidak valid.", show_alert=True)
        return

    async with UnitOfWork(session_factory) as uow:
        order = await uow.orders.get(order_id)
        if order is None:
            await callback.answer("❌ Pesanan tidak ditemukan.", show_alert=True)
            return

        # Validate the transition
        transitions: dict[str, list[str]] = {
            OrderStatus.PENDING.value: [OrderStatus.AWAITING_PAYMENT.value, OrderStatus.CANCELLED.value],
            OrderStatus.AWAITING_PAYMENT.value: [OrderStatus.PAID.value, OrderStatus.CANCELLED.value],
            OrderStatus.PAID.value: [OrderStatus.SHIPPED.value, OrderStatus.CANCELLED.value],
            OrderStatus.SHIPPED.value: [OrderStatus.DELIVERED.value],
            OrderStatus.DELIVERED.value: [],
            OrderStatus.CANCELLED.value: [],
        }

        if new_status_str not in transitions.get(order.status, []):
            await callback.answer(
                f"❌ Tidak dapat mengubah dari {order.status} ke {new_status_str}.",
                show_alert=True,
            )
            return

        # If cancelling, release stock
        if new_status == OrderStatus.CANCELLED:
            items = await uow.order_items.list_by_order(order_id)
            for item in items:
                await uow.products.release_stock(item.product_id, item.quantity)

        await uow.orders.update_status(order_id, new_status)

    await callback.answer(fmt_order_status_updated(order_id, new_status_str))
    # Re-show detail
    await cb_admin_ord_detail(callback, session_factory)


# ══════════════════════════════════════════════════════════
#  BROADCAST
# ══════════════════════════════════════════════════════════


@router.callback_query(lambda c: c.data == "adm:bcast")
async def cb_admin_bcast(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start broadcast FSM → ask for message."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    await state.set_state(Broadcast.message)
    await callback.message.answer(fmt_ask_broadcast_message())
    await callback.answer()


@router.message(StateFilter(Broadcast.message))
async def process_bcast_message(message: types.Message, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Receive broadcast message → show preview + confirm."""
    if not message.text:
        await message.answer("⚠️ Ketik pesan broadcast sebagai teks.")
        return

    broadcast_text = message.text.strip()
    await state.update_data(bcast_text=broadcast_text)

    # Count recipients
    async with UnitOfWork(session_factory) as uow:
        from sqlalchemy import func, select

        from ...infrastructure.persistence.models import User
        stmt = select(func.count()).select_from(User)
        result = await uow.session.execute(stmt)
        recipient_count = result.scalar_one()

    from ...shared.keyboards import admin_broadcast_confirm_kb
    kb = admin_broadcast_confirm_kb()

    await state.set_state(Broadcast.confirm)
    await message.answer(
        fmt_broadcast_preview(recipient_count, broadcast_text),
        reply_markup=kb,
    )


@router.callback_query(lambda c: c.data == "adm:bcast_go", StateFilter(Broadcast.confirm))
async def cb_bcast_confirm(callback: types.CallbackQuery, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Confirm broadcast → send message to all users."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    data = await state.get_data()
    broadcast_text = data.get("bcast_text", "")
    if not broadcast_text:
        await state.clear()
        await callback.answer("❌ Tidak ada pesan broadcast.", show_alert=True)
        return

    async with UnitOfWork(session_factory) as uow:
        from sqlalchemy import select

        from ...infrastructure.persistence.models import User
        stmt = select(User)
        result = await uow.session.execute(stmt)
        users = list(result.scalars().all())

    success = 0
    failed = 0

    for user in users:
        try:
            await callback.bot.send_message(
                chat_id=user.id,
                text=f"📢 **Broadcast**\n\n{broadcast_text}",
            )
            success += 1
        except Exception as exc:
            logger.warning("broadcast failed for user %d: %s", user.id, exc)
            failed += 1

    await state.clear()
    await callback.message.answer(fmt_broadcast_sent(success, failed))
    await callback.answer()


@router.callback_query(lambda c: c.data == "adm:bcast_no", StateFilter(Broadcast.confirm))
async def cb_bcast_cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel broadcast."""
    await state.clear()
    await callback.message.answer(fmt_broadcast_cancelled())
    await callback.answer("Dibatalkan.")


# ══════════════════════════════════════════════════════════
#  COUPON MANAGEMENT
# ══════════════════════════════════════════════════════════


@router.callback_query(lambda c: c.data == "adm:cpns")
async def cb_admin_coupons(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Show the admin coupon list."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    async with UnitOfWork(session_factory) as uow:
        coupons = await uow.coupons.list_all()

    text = fmt_coupon_list(coupons)

    from ...shared.keyboards import admin_coupon_list_kb
    kb = admin_coupon_list_kb(coupons)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("adm:cpn:") and not c.data.startswith("adm:cpn_tog:") and not c.data.startswith("adm:cpn_del:"))
async def cb_admin_coupon_detail(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Show coupon detail for admin management."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:cpn:"):]
    if not payload.isdigit():
        await callback.answer("❌ Kupon tidak valid.", show_alert=True)
        return

    coupon_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        coupon = await uow.coupons.get(coupon_id)

    if coupon is None:
        await callback.answer("❌ Kupon tidak ditemukan.", show_alert=True)
        return

    text = fmt_coupon_detail(coupon)

    from ...shared.keyboards import admin_coupon_detail_kb
    kb = admin_coupon_detail_kb(coupon_id, is_active=coupon.is_active)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


# ── Coupon: Create (FSM) ───────────────────────────────


@router.callback_query(lambda c: c.data == "adm:cpn_new")
async def cb_admin_coupon_new(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Start new-coupon FSM → ask for code."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    await state.set_state(CouponCreate.code)
    await callback.message.answer(fmt_ask_coupon_code())
    await callback.answer()


@router.message(StateFilter(CouponCreate.code))
async def process_coupon_new_code(message: types.Message, state: FSMContext) -> None:
    """Receive new coupon code → ask for discount percentage."""
    if not message.text:
        await message.answer("⚠️ Ketik kode kupon sebagai teks.")
        return

    code = message.text.strip().upper()
    if len(code) < 2:
        await message.answer("⚠️ Kode terlalu pendek (min 2 karakter).")
        return

    await state.update_data(coupon_code=code)
    await state.set_state(CouponCreate.discount_percent)
    await message.answer(fmt_ask_coupon_discount())


@router.message(StateFilter(CouponCreate.discount_percent))
async def process_coupon_new_discount(message: types.Message, state: FSMContext) -> None:
    """Receive discount percentage → ask for max uses."""
    if not message.text:
        await message.answer("⚠️ Ketik persentase diskon sebagai angka.")
        return

    try:
        discount = int(message.text.strip().replace("%", ""))
    except ValueError:
        await message.answer("⚠️ Persentase tidak valid. Ketik angka (1-100):")
        return

    if not 1 <= discount <= 100:
        await message.answer("⚠️ Persentase harus antara 1-100.")
        return

    await state.update_data(coupon_discount=discount)
    await state.set_state(CouponCreate.max_uses)
    await message.answer(fmt_ask_coupon_max_uses())


@router.message(StateFilter(CouponCreate.max_uses))
async def process_coupon_new_max_uses(message: types.Message, state: FSMContext) -> None:
    """Receive max uses → ask for expiry date."""
    text = message.text.strip() if message.text else ""
    max_uses = None

    if text != "/skip":
        try:
            max_uses = int(text)
        except ValueError:
            await message.answer("⚠️ Jumlah tidak valid. Ketik angka atau /skip:")
            return
        if max_uses < 1:
            await message.answer("⚠️ Jumlah harus ≥ 1 atau /skip untuk tanpa batas.")
            return

    await state.update_data(coupon_max_uses=max_uses)
    await state.set_state(CouponCreate.expires_at)
    await message.answer(fmt_ask_coupon_expires())


@router.message(StateFilter(CouponCreate.expires_at))
async def process_coupon_new_expires(message: types.Message, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Receive expiry date → create the coupon."""
    text = message.text.strip() if message.text else ""
    expires_at = None

    if text != "/skip":
        from datetime import datetime as _dt
        try:
            expires_at = _dt.strptime(text, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59,
                tzinfo=UTC,
            )
        except ValueError:
            await message.answer("⚠️ Format tidak valid. Ketik YYYY-MM-DD atau /skip:")
            return

    data = await state.get_data()
    code = data.get("coupon_code", "")
    discount = data.get("coupon_discount", 0)
    max_uses = data.get("coupon_max_uses")

    async with UnitOfWork(session_factory) as uow:
        # Check code uniqueness
        existing = await uow.coupons.get_by_code(code)
        if existing is not None:
            await message.answer(
                f"⚠️ Kode '{code}' sudah digunakan. Ketik kode lain:"
            )
            return  # Stay in same state for retry

        coupon = await uow.coupons.create(
            code=code,
            discount_percent=discount,
            max_uses=max_uses,
            expires_at=expires_at,
        )

    await state.clear()
    await message.answer(fmt_coupon_created(coupon))


# ── Coupon: Toggle ─────────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("adm:cpn_tog:"))
async def cb_admin_coupon_toggle(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Toggle coupon active/inactive."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:cpn_tog:"):]
    if not payload.isdigit():
        await callback.answer("❌ Kupon tidak valid.", show_alert=True)
        return

    coupon_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        coupon = await uow.coupons.get(coupon_id)
        if coupon is None:
            await callback.answer("❌ Kupon tidak ditemukan.", show_alert=True)
            return
        new_active = not coupon.is_active
        await uow.coupons.toggle_active(coupon_id, is_active=new_active)

    status = "diaktifkan" if new_active else "dinonaktifkan"
    await callback.answer(f"✅ Kupon {status}.")
    # Re-show detail
    await cb_admin_coupon_detail(callback, session_factory)


# ── Coupon: Delete ──────────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("adm:cpn_del:"))
async def cb_admin_coupon_delete(callback: types.CallbackQuery, session_factory) -> None:  # type: ignore[valid-type]
    """Delete a coupon."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:cpn_del:"):]
    if not payload.isdigit():
        await callback.answer("❌ Kupon tidak valid.", show_alert=True)
        return

    coupon_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        coupon = await uow.coupons.get(coupon_id)
        if coupon is None:
            await callback.answer("❌ Kupon tidak ditemukan.", show_alert=True)
            return
        await uow.coupons.delete(coupon_id)

    await callback.answer("🗑️ Kupon dihapus.")
    # Go back to coupon list
    await cb_admin_coupons(callback, session_factory)


# ══════════════════════════════════════════════════════════
#  PRODUCT IMAGE MANAGEMENT
# ══════════════════════════════════════════════════════════


@router.callback_query(lambda c: c.data and c.data.startswith("adm:prd_img:"))
async def cb_admin_prd_images(callback: types.CallbackQuery, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Show product images management page."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:prd_img:"):]
    if not payload.isdigit():
        await callback.answer("❌ Produk tidak valid.", show_alert=True)
        return

    product_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        product = await uow.products.get(product_id)
        if product is None:
            await callback.answer("❌ Produk tidak ditemukan.", show_alert=True)
            return
        images = await uow.product_images.list_by_product(product_id)

    # Set product_id in FSM data for the upload handler
    await state.update_data(img_product_id=product_id)
    await state.set_state(ProductImageUpload.photo)

    text = fmt_product_images(product, images)

    from ...shared.keyboards import admin_product_images_kb
    kb = admin_product_images_kb(product_id, images)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
    await callback.answer()


@router.message(StateFilter(ProductImageUpload.photo), lambda m: m.photo is not None)
async def process_product_image_upload(message: types.Message, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Receive a photo and save it as a product image."""
    if not _is_admin(message.from_user.id):
        await message.answer(fmt_not_admin())
        return

    # Get the highest resolution photo
    photo = message.photo[-1]
    file_id = photo.file_id

    data = await state.get_data()
    product_id = data.get("img_product_id")

    if product_id is None:
        await state.clear()
        await message.answer("❌ Sesi upload gambar kadaluarsa. Silakan coba lagi.")
        return

    async with UnitOfWork(session_factory) as uow:
        # Determine position (append to end)
        existing_images = await uow.product_images.list_by_product(product_id)
        position = len(existing_images)
        is_cover = len(existing_images) == 0  # First image is automatically the cover

        image = await uow.product_images.create(
            product_id=product_id,
            file_id=file_id,
            position=position,
            is_cover=is_cover,
        )

    await message.answer(fmt_product_image_added(image))

    # Re-show the images page
    async with UnitOfWork(session_factory) as uow:
        product = await uow.products.get(product_id)
        images = await uow.product_images.list_by_product(product_id)

    from ...shared.keyboards import admin_product_images_kb
    text = fmt_product_images(product, images)
    kb = admin_product_images_kb(product_id, images)

    # Stay in the photo upload state so admin can keep adding images
    await message.answer(text, reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith("adm:prd_img_cov:"))
async def cb_admin_prd_img_cover(callback: types.CallbackQuery, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Set a product image as the cover."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:prd_img_cov:"):]
    if not payload.isdigit():
        await callback.answer("❌ Gambar tidak valid.", show_alert=True)
        return

    image_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        await uow.product_images.set_cover(image_id)

    await callback.answer(fmt_product_image_cover_set(image_id))

    # Re-show images by finding the product_id
    async with UnitOfWork(session_factory) as uow:
        image = await uow.product_images.get(image_id)
    if image is not None:
        await _reshow_product_images(callback, state, image.product_id, session_factory)


@router.callback_query(lambda c: c.data and c.data.startswith("adm:prd_img_del:"))
async def cb_admin_prd_img_delete(callback: types.CallbackQuery, state: FSMContext, session_factory) -> None:  # type: ignore[valid-type]
    """Delete a product image."""
    if not _is_admin(callback.from_user.id):
        await callback.answer(fmt_not_admin(), show_alert=True)
        return

    assert callback.data is not None
    payload = callback.data[len("adm:prd_img_del:"):]
    if not payload.isdigit():
        await callback.answer("❌ Gambar tidak valid.", show_alert=True)
        return

    image_id = int(payload)

    async with UnitOfWork(session_factory) as uow:
        image = await uow.product_images.get(image_id)
        if image is None:
            await callback.answer("❌ Gambar tidak ditemukan.", show_alert=True)
            return
        product_id = image.product_id
        await uow.product_images.delete(image_id)

    await callback.answer(fmt_product_image_deleted(image_id))

    # Re-show images
    await _reshow_product_images(callback, state, product_id, session_factory)


# ── Product images helper ──────────────────────────────


async def _reshow_product_images(
    callback: types.CallbackQuery,
    state: FSMContext,
    product_id: int,
    session_factory,
) -> None:
    """Re-display the product images management page."""
    async with UnitOfWork(session_factory) as uow:
        product = await uow.products.get(product_id)
        images = await uow.product_images.list_by_product(product_id)

    await state.update_data(img_product_id=product_id)

    text = fmt_product_images(product, images)

    from ...shared.keyboards import admin_product_images_kb
    kb = admin_product_images_kb(product_id, images)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)
