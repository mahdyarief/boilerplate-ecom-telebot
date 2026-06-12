"""Keyboard builders — reusable inline-keyboard factory functions.

Every builder returns an ``InlineKeyboardMarkup`` with properly
callback-data-encoded payloads.  Callback data format is documented
per builder.

All callback patterns MUST be ≤64 bytes (Telegram limit).
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# ── Callback data prefixes ───────────────────────────────

PREFIX_CATEGORY = "cat:"
PREFIX_PRODUCT = "prd:"
PREFIX_CART_ADD = "add:"
PREFIX_CART_REMOVE = "rm:"
PREFIX_CART_QTY = "qty:"
PREFIX_CART_CLEAR = "cc:"
PREFIX_CART_BACK = "cbk:"
PREFIX_BACK_CATALOG = "bck:cat"
PREFIX_BACK_ROOT = "bck:root"

# ── Checkout prefixes ───────────────────────────────────
PREFIX_CHECKOUT = "cko:"

# ── Orders prefixes ─────────────────────────────────────
PREFIX_ORDER = "ord:"
PREFIX_ORDER_CANCEL = "ord_cancel:"
PREFIX_ORDERS_BACK = "ord_bck:"

# ── Admin prefixes ──────────────────────────────────────
PREFIX_ADMIN = "adm:"
PREFIX_ADMIN_CATS = "adm:cats"
PREFIX_ADMIN_CAT_NEW = "adm:cat_new"
PREFIX_ADMIN_CAT = "adm:cat:"
PREFIX_ADMIN_CAT_EDIT = "adm:cat_edit:"
PREFIX_ADMIN_CAT_TOGGLE = "adm:cat_tog:"
PREFIX_ADMIN_CAT_DEL = "adm:cat_del:"
PREFIX_ADMIN_PRDS = "adm:prds"
PREFIX_ADMIN_PRD_NEW = "adm:prd_new"
PREFIX_ADMIN_PRD = "adm:prd:"
PREFIX_ADMIN_PRD_EDIT = "adm:prd_edit:"
PREFIX_ADMIN_PRD_TOGGLE = "adm:prd_tog:"
PREFIX_ADMIN_PRD_DEL = "adm:prd_del:"
PREFIX_ADMIN_ORDS = "adm:ords"
PREFIX_ADMIN_ORD = "adm:ord:"
PREFIX_ADMIN_ORD_STATUS = "adm:ord_st:"
PREFIX_ADMIN_BCAST = "adm:bcast"
PREFIX_ADMIN_BCAST_CONFIRM = "adm:bcast_go"
PREFIX_ADMIN_BCAST_CANCEL = "adm:bcast_no"
PREFIX_ADMIN_BACK = "adm:back"
PREFIX_ADMIN_PRD_NEW_CAT = "adm:prd_ncat:"

# ── Coupon prefixes ────────────────────────────────────
PREFIX_ADMIN_COUPONS = "adm:cpns"
PREFIX_ADMIN_COUPON = "adm:cpn:"
PREFIX_ADMIN_COUPON_NEW = "adm:cpn_new"
PREFIX_ADMIN_COUPON_TOGGLE = "adm:cpn_tog:"
PREFIX_ADMIN_COUPON_DEL = "adm:cpn_del:"

# ── Product image prefixes ────────────────────────────
PREFIX_ADMIN_PRD_IMGS = "adm:prd_img:"
PREFIX_ADMIN_PRD_IMG_COVER = "adm:prd_img_cov:"
PREFIX_ADMIN_PRD_IMG_DEL = "adm:prd_img_del:"

# ── Checkout coupon prefixes ────────────────────────────
PREFIX_CHECKOUT_COUPON = "cko_coupon:"

# ── Order reorder prefix ────────────────────────────────
PREFIX_ORDER_REORDER = "ord_reorder:"


# ── Catalog keyboards ────────────────────────────────────


def categories_kb(categories: list, *, back_text: str = "🔙 Kembali") -> InlineKeyboardMarkup:
    """Root category list.

    Callback data: ``cat:<category_id>``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=cat.name, callback_data=f"{PREFIX_CATEGORY}{cat.id}")]
        for cat in categories
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def subcategories_or_products_kb(
    parent_id: int,
    subcategories: list,
    *,
    back_text: str = "⬅️ Kembali",
) -> InlineKeyboardMarkup:
    """Subcategory list (products are shown in the message body).

    Callback data:
    * subcategory → ``cat:<subcategory_id>``
    * back → ``bck:cat:<parent_id>``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=sc.name, callback_data=f"{PREFIX_CATEGORY}{sc.id}")]
        for sc in subcategories
    ]
    buttons.append(
        [InlineKeyboardButton(text=back_text, callback_data=f"{PREFIX_BACK_CATALOG}:{parent_id}")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_detail_kb(
    product_id: int,
    category_id: int,
    *,
    add_text: str = "🛒 Tambah ke Keranjang",
    back_text: str = "⬅️ Kembali",
    root_text: str = "🏠 Katalog",
) -> InlineKeyboardMarkup:
    """Product detail page — add to cart + navigation.

    Callback data:
    * add → ``add:<product_id>``
    * back (to category products) → ``bck:cat:<category_id>``
    * root (categories) → ``bck:root``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=add_text, callback_data=f"{PREFIX_CART_ADD}{product_id}")],
        [InlineKeyboardButton(text=back_text, callback_data=f"{PREFIX_BACK_CATALOG}:{category_id}")],
        [InlineKeyboardButton(text=root_text, callback_data=PREFIX_BACK_ROOT)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Cart keyboards ───────────────────────────────────────


def cart_item_kb(
    cart_item_id: int,
    quantity: int,
    *,
    minus_text: str = "\u2796",
    plus_text: str = "\u2795",
    remove_text: str = "🗑️ Hapus",
) -> InlineKeyboardMarkup:
    """Per-item controls: minus / qty / plus + remove.

    Callback data:
    * minus → ``qty:<cart_item_id>:-``
    * plus  → ``qty:<cart_item_id>:+``
    * remove → ``rm:<cart_item_id>``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text=minus_text, callback_data=f"{PREFIX_CART_QTY}{cart_item_id}:-"),
            InlineKeyboardButton(text=str(quantity), callback_data="noop"),
            InlineKeyboardButton(text=plus_text, callback_data=f"{PREFIX_CART_QTY}{cart_item_id}:+"),
        ],
        [InlineKeyboardButton(text=remove_text, callback_data=f"{PREFIX_CART_REMOVE}{cart_item_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cart_footer_kb(
    *,
    checkout_text: str = "💳 Checkout",
    clear_text: str = "🧹 Kosongkan",
    catalog_text: str = "🛍️ Lanjut Belanja",
) -> InlineKeyboardMarkup:
    """Cart-level: checkout, clear all + continue shopping.

    Callback data:
    * checkout → ``cko:start``
    * clear    → ``cc:``
    * catalog  → ``bck:root``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=checkout_text, callback_data=f"{PREFIX_CHECKOUT}start")],
        [InlineKeyboardButton(text=catalog_text, callback_data=PREFIX_BACK_ROOT)],
        [InlineKeyboardButton(text=clear_text, callback_data=PREFIX_CART_CLEAR)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_clear_kb(
    *,
    yes_text: str = "✅ Ya, kosongkan",
    no_text: str = "❌ Batal",
) -> InlineKeyboardMarkup:
    """Confirm clearing the entire cart.

    Callback data:
    * yes → ``cc:yes``
    * no  → ``cc:no``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=yes_text, callback_data=f"{PREFIX_CART_CLEAR}yes")],
        [InlineKeyboardButton(text=no_text, callback_data=f"{PREFIX_CART_CLEAR}no")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Checkout keyboards ──────────────────────────────────


def checkout_confirm_kb(
    *,
    confirm_text: str = "✅ Konfirmasi & Bayar",
    cancel_text: str = "❌ Batal",
) -> InlineKeyboardMarkup:
    """Checkout review page — confirm or cancel.

    Callback data:
    * confirm → ``cko:confirm``
    * cancel  → ``cko:cancel``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=confirm_text, callback_data=f"{PREFIX_CHECKOUT}confirm")],
        [InlineKeyboardButton(text=cancel_text, callback_data=f"{PREFIX_CHECKOUT}cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Orders keyboards ────────────────────────────────────


def orders_list_kb(orders: list, *, currency: str = "IDR") -> InlineKeyboardMarkup:
    """List of orders — tap to view details.

    Callback data: ``ord:<order_id>``
    """
    from .money import Money as _Money

    buttons: list[list[InlineKeyboardButton]] = []
    for order in orders[:10]:  # Telegram inline keyboard limit
        total_str = _Money(order.total_smallest_unit, currency).format()
        buttons.append([
            InlineKeyboardButton(
                text=f"#{order.id} — {total_str} ({order.status})",
                callback_data=f"{PREFIX_ORDER}{order.id}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def order_detail_kb(
    order_id: int,
    *,
    cancellable: bool = False,
    reorderable: bool = False,
    cancel_text: str = "❌ Batalkan Pesanan",
    reorder_text: str = "🛒 Pesan Lagi",
    back_text: str = "⬅️ Kembali",
) -> InlineKeyboardMarkup:
    """Order detail page — cancel / reorder (if allowed) + back to list.

    Callback data:
    * cancel  → ``ord_cancel:<order_id>``
    * reorder → ``ord_reorder:<order_id>``
    * back    → ``ord_bck:``
    """
    buttons: list[list[InlineKeyboardButton]] = []
    if cancellable:
        buttons.append([
            InlineKeyboardButton(
                text=cancel_text,
                callback_data=f"{PREFIX_ORDER_CANCEL}{order_id}",
            )
        ])
    if reorderable:
        buttons.append([
            InlineKeyboardButton(
                text=reorder_text,
                callback_data=f"{PREFIX_ORDER_REORDER}{order_id}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text=back_text, callback_data=PREFIX_ORDERS_BACK)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Admin keyboards ──────────────────────────────────────


def admin_panel_kb() -> InlineKeyboardMarkup:
    """Admin panel landing — top-level actions.

    Callback data:
    * categories → ``adm:cats``
    * products   → ``adm:prds``
    * orders     → ``adm:ords``
    * coupons    → ``adm:cpns``
    * broadcast  → ``adm:bcast``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="📂 Kategori", callback_data=PREFIX_ADMIN_CATS)],
        [InlineKeyboardButton(text="📦 Produk", callback_data=PREFIX_ADMIN_PRDS)],
        [InlineKeyboardButton(text="📋 Pesanan", callback_data=PREFIX_ADMIN_ORDS)],
        [InlineKeyboardButton(text="🎟️ Kupon", callback_data=PREFIX_ADMIN_COUPONS)],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data=PREFIX_ADMIN_BCAST)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_category_list_kb(
    categories: list,
    *,
    include_inactive: bool = True,
) -> InlineKeyboardMarkup:
    """Admin category list — tap to manage a category.

    Callback data:
    * category → ``adm:cat:<category_id>``
    * new      → ``adm:cat_new``
    * back     → ``adm:back``
    """
    buttons: list[list[InlineKeyboardButton]] = []

    shown = categories if include_inactive else [c for c in categories if c.is_active]
    for cat in shown:
        status = "✅" if cat.is_active else "❌"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {cat.name}",
                callback_data=f"{PREFIX_ADMIN_CAT}{cat.id}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="➕ Kategori Baru", callback_data=PREFIX_ADMIN_CAT_NEW)
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Kembali", callback_data=PREFIX_ADMIN_BACK)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_category_detail_kb(category_id: int, *, is_active: bool = True) -> InlineKeyboardMarkup:
    """Admin category detail — edit / toggle / delete.

    Callback data:
    * edit   → ``adm:cat_edit:<category_id>``
    * toggle → ``adm:cat_tog:<category_id>``
    * delete → ``adm:cat_del:<category_id>``
    * back   → ``adm:cats``
    """
    toggle_text = "❌ Nonaktifkan" if is_active else "✅ Aktifkan"
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✏️ Edit", callback_data=f"{PREFIX_ADMIN_CAT_EDIT}{category_id}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"{PREFIX_ADMIN_CAT_TOGGLE}{category_id}")],
        [InlineKeyboardButton(text="🗑️ Hapus", callback_data=f"{PREFIX_ADMIN_CAT_DEL}{category_id}")],
        [InlineKeyboardButton(text="⬅️ Kembali", callback_data=PREFIX_ADMIN_CATS)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_category_edit_field_kb(category_id: int) -> InlineKeyboardMarkup:
    """Pick which category field to edit.

    Callback data for each field: ``adm:cat_edit:<category_id>:<field_name>``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(
            text="📝 Nama",
            callback_data=f"{PREFIX_ADMIN_CAT_EDIT}{category_id}:name",
        )],
        [InlineKeyboardButton(
            text="📝 Slug",
            callback_data=f"{PREFIX_ADMIN_CAT_EDIT}{category_id}:slug",
        )],
        [InlineKeyboardButton(
            text="📝 Posisi",
            callback_data=f"{PREFIX_ADMIN_CAT_EDIT}{category_id}:position",
        )],
        [InlineKeyboardButton(
            text="⬅️ Batal",
            callback_data=f"{PREFIX_ADMIN_CAT}{category_id}",
        )],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_product_list_kb(
    products: list,
    *,
    include_inactive: bool = True,
) -> InlineKeyboardMarkup:
    """Admin product list — tap to manage a product.

    Callback data:
    * product → ``adm:prd:<product_id>``
    * new      → ``adm:prd_new``
    * back     → ``adm:back``
    """
    buttons: list[list[InlineKeyboardButton]] = []

    shown = products if include_inactive else [p for p in products if p.is_active]
    for p in shown:
        status = "✅" if p.is_active else "❌"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {p.name}",
                callback_data=f"{PREFIX_ADMIN_PRD}{p.id}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="➕ Produk Baru", callback_data=PREFIX_ADMIN_PRD_NEW)
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Kembali", callback_data=PREFIX_ADMIN_BACK)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_product_detail_kb(product_id: int, *, is_active: bool = True) -> InlineKeyboardMarkup:
    """Admin product detail — edit / toggle / delete / images.

    Callback data:
    * edit   → ``adm:prd_edit:<product_id>``
    * images → ``adm:prd_img:<product_id>``
    * toggle → ``adm:prd_tog:<product_id>``
    * delete → ``adm:prd_del:<product_id>``
    * back   → ``adm:prds``
    """
    toggle_text = "❌ Nonaktifkan" if is_active else "✅ Aktifkan"
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✏️ Edit", callback_data=f"{PREFIX_ADMIN_PRD_EDIT}{product_id}")],
        [InlineKeyboardButton(text="🖼️ Kelola Gambar", callback_data=f"{PREFIX_ADMIN_PRD_IMGS}{product_id}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"{PREFIX_ADMIN_PRD_TOGGLE}{product_id}")],
        [InlineKeyboardButton(text="🗑️ Hapus", callback_data=f"{PREFIX_ADMIN_PRD_DEL}{product_id}")],
        [InlineKeyboardButton(text="⬅️ Kembali", callback_data=PREFIX_ADMIN_PRDS)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_product_edit_field_kb(product_id: int) -> InlineKeyboardMarkup:
    """Pick which product field to edit.

    Callback data for each field: ``adm:prd_edit:<product_id>:<field_name>``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(
            text="📝 Nama",
            callback_data=f"{PREFIX_ADMIN_PRD_EDIT}{product_id}:name",
        )],
        [InlineKeyboardButton(
            text="📝 Deskripsi",
            callback_data=f"{PREFIX_ADMIN_PRD_EDIT}{product_id}:description",
        )],
        [InlineKeyboardButton(
            text="📝 Harga",
            callback_data=f"{PREFIX_ADMIN_PRD_EDIT}{product_id}:price",
        )],
        [InlineKeyboardButton(
            text="📝 Stok",
            callback_data=f"{PREFIX_ADMIN_PRD_EDIT}{product_id}:stock",
        )],
        [InlineKeyboardButton(
            text="⬅️ Batal",
            callback_data=f"{PREFIX_ADMIN_PRD}{product_id}",
        )],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_product_new_category_kb(categories: list) -> InlineKeyboardMarkup:
    """Select category when creating a new product.

    Callback data: ``adm:prd_ncat:<category_id>``
    """
    buttons: list[list[InlineKeyboardButton]] = []
    for cat in categories:
        if cat.is_active:
            buttons.append([
                InlineKeyboardButton(
                    text=cat.name,
                    callback_data=f"{PREFIX_ADMIN_PRD_NEW_CAT}{cat.id}",
                )
            ])

    buttons.append([
        InlineKeyboardButton(text="❌ Batal", callback_data=PREFIX_ADMIN_PRDS)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_order_list_kb(orders: list, *, currency: str = "IDR") -> InlineKeyboardMarkup:
    """Admin list of orders — tap to manage.

    Callback data: ``adm:ord:<order_id>``
    """
    from .money import Money as _Money

    buttons: list[list[InlineKeyboardButton]] = []
    for order in orders[:10]:
        total_str = _Money(order.total_smallest_unit, currency).format()
        buttons.append([
            InlineKeyboardButton(
                text=f"#{order.id} — {total_str} ({order.status})",
                callback_data=f"{PREFIX_ADMIN_ORD}{order.id}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Kembali", callback_data=PREFIX_ADMIN_BACK)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_order_detail_kb(
    order_id: int,
    status: str,
) -> InlineKeyboardMarkup:
    """Admin order detail — status transition buttons.

    Callback data: ``adm:ord_st:<order_id>:<new_status>``
    """
    from ..core.constants import OrderStatus

    # Determine valid next statuses from the current one
    transitions: dict[str, list[str]] = {
        OrderStatus.PENDING.value: [OrderStatus.AWAITING_PAYMENT.value, OrderStatus.CANCELLED.value],
        OrderStatus.AWAITING_PAYMENT.value: [OrderStatus.PAID.value, OrderStatus.CANCELLED.value],
        OrderStatus.PAID.value: [OrderStatus.SHIPPED.value, OrderStatus.CANCELLED.value],
        OrderStatus.SHIPPED.value: [OrderStatus.DELIVERED.value],
        OrderStatus.DELIVERED.value: [],
        OrderStatus.CANCELLED.value: [],
    }

    status_labels: dict[str, str] = {
        OrderStatus.AWAITING_PAYMENT.value: "💳 Menunggu Pembayaran",
        OrderStatus.PAID.value: "✅ Sudah Dibayar",
        OrderStatus.SHIPPED.value: "🚚 Dikirim",
        OrderStatus.DELIVERED.value: "📦 Diterima",
        OrderStatus.CANCELLED.value: "❌ Dibatalkan",
    }

    next_statuses = transitions.get(status, [])

    buttons: list[list[InlineKeyboardButton]] = []
    for ns in next_statuses:
        label = status_labels.get(ns, ns)
        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"{PREFIX_ADMIN_ORD_STATUS}{order_id}:{ns}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="⬅️ Kembali", callback_data=PREFIX_ADMIN_ORDS)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_broadcast_confirm_kb() -> InlineKeyboardMarkup:
    """Confirm or cancel a broadcast.

    Callback data:
    * confirm → ``adm:bcast_go``
    * cancel  → ``adm:bcast_no``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="✅ Kirim Broadcast", callback_data=PREFIX_ADMIN_BCAST_CONFIRM)],
        [InlineKeyboardButton(text="❌ Batal", callback_data=PREFIX_ADMIN_BCAST_CANCEL)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_back_kb(target: str = PREFIX_ADMIN_BACK) -> InlineKeyboardMarkup:
    """Simple back button for admin pages.

    Parameters
    ----------
    target : str
        Callback data for the back button.  Defaults to ``adm:back``.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Kembali", callback_data=target)]
        ]
    )


# ── Coupon keyboards (Phase 6) ────────────────────────


def admin_coupon_list_kb(coupons: list) -> InlineKeyboardMarkup:
    """Admin coupon list — tap to manage a coupon.

    Callback data:
    * coupon  → ``adm:cpn:<coupon_id>``
    * new     → ``adm:cpn_new``
    * back    → ``adm:back``
    """
    buttons: list[list[InlineKeyboardButton]] = []
    for c in coupons:
        status = "✅" if c.is_active else "❌"
        uses_display = f"{c.used_count}/{c.max_uses}" if c.max_uses else str(c.used_count)
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {c.code} — {c.discount_percent}% ({uses_display})",
                callback_data=f"{PREFIX_ADMIN_COUPON}{c.id}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="➕ Kupon Baru", callback_data=PREFIX_ADMIN_COUPON_NEW)
    ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Kembali", callback_data=PREFIX_ADMIN_BACK)
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_coupon_detail_kb(coupon_id: int, *, is_active: bool = True) -> InlineKeyboardMarkup:
    """Admin coupon detail — toggle / delete.

    Callback data:
    * toggle → ``adm:cpn_tog:<coupon_id>``
    * delete → ``adm:cpn_del:<coupon_id>``
    * back   → ``adm:cpns``
    """
    toggle_text = "❌ Nonaktifkan" if is_active else "✅ Aktifkan"
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=toggle_text, callback_data=f"{PREFIX_ADMIN_COUPON_TOGGLE}{coupon_id}")],
        [InlineKeyboardButton(text="🗑️ Hapus", callback_data=f"{PREFIX_ADMIN_COUPON_DEL}{coupon_id}")],
        [InlineKeyboardButton(text="⬅️ Kembali", callback_data=PREFIX_ADMIN_COUPONS)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Checkout coupon keyboard (Phase 6) ─────────────────


def checkout_coupon_kb(
    *,
    apply_text: str = "🎟️ Gunakan Kupon",
    skip_text: str = "⏭️ Tanpa Kupon",
) -> InlineKeyboardMarkup:
    """Checkout coupon prompt — apply or skip.

    Callback data:
    * apply → ``cko_coupon:apply``
    * skip  → ``cko_coupon:skip``
    """
    buttons: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=apply_text, callback_data=f"{PREFIX_CHECKOUT_COUPON}apply")],
        [InlineKeyboardButton(text=skip_text, callback_data=f"{PREFIX_CHECKOUT_COUPON}skip")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Product image keyboards (Phase 6) ──────────────────


def admin_product_images_kb(
    product_id: int,
    images: list,
) -> InlineKeyboardMarkup:
    """Admin product image management.

    Callback data:
    * set cover → ``adm:prd_img_cov:<image_id>``
    * delete    → ``adm:prd_img_del:<image_id>``
    * back      → ``adm:prd:<product_id>``
    """
    buttons: list[list[InlineKeyboardButton]] = []
    for img in images:
        cover_flag = "⭐" if img.is_cover else "   "
        buttons.append([
            InlineKeyboardButton(
                text=f"{cover_flag} Gambar #{img.id} (pos: {img.position})",
                callback_data=f"noop_{img.id}",  # display only
            )
        ])
    # Action buttons
    for img in images:
        if not img.is_cover:
            buttons.append([
                InlineKeyboardButton(
                    text=f"⭐ Set Cover #{img.id}",
                    callback_data=f"{PREFIX_ADMIN_PRD_IMG_COVER}{img.id}",
                )
            ])
        buttons.append([
            InlineKeyboardButton(
                text=f"🗑️ Hapus #{img.id}",
                callback_data=f"{PREFIX_ADMIN_PRD_IMG_DEL}{img.id}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="⬅️ Kembali", callback_data=f"{PREFIX_ADMIN_PRD}{product_id}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
