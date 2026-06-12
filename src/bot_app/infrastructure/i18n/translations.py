"""Lightweight i18n — translation dictionaries and ``t()`` helper.

Phase 6 provides a simple dict-based i18n system without external
dependencies.  Each language is a flat dictionary of message keys
to translated strings.  The ``t(key, lang)`` function looks up the
key in the requested language and falls back to the default language.

To add a new language:
1. Add a dict to ``_TRANSLATIONS`` keyed by ISO-639-1 code.
2. Provide translations for all keys used in the UI.
3. Set the new language code in ``User.language``.

The key convention is ``<feature>.<message_id>`` using dot notation,
e.g. ``cart.empty`` or ``checkout.address_prompt``.
"""

from __future__ import annotations

from ...core.config import settings

# ── Translation dictionaries ────────────────────────────────

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "id": {
        # ── start ───────────────────────────────────────────
        "start.welcome": "Selamat datang di {shop_name}!",
        "start.help_header": "Perintah yang tersedia:",
        # ── catalog ────────────────────────────────────────
        "catalog.empty": "Katalog kosong — belum ada kategori.",
        "catalog.select_category": "Pilih kategori:",
        "catalog.no_products": "Tidak ada produk di kategori ini.",
        "catalog.out_of_stock": "Stok habis",
        # ── cart ────────────────────────────────────────────
        "cart.empty": "Keranjang Anda kosong.",
        "cart.start_shopping": "Ketik /catalog untuk mulai belanja!",
        "cart.title": "Keranjang Anda:",
        "cart.total": "Total",
        "cart.updated": "Jumlah diperbarui.",
        "cart.added": "ditambahkan ke keranjang!",
        "cart.removed": "dihapus dari keranjang.",
        "cart.cleared": "Keranjang dikosongkan.",
        "cart.clear_confirm": "Yakin ingin mengosongkan keranjang?",
        "cart.insufficient_stock": "Stok tidak cukup!",
        "cart.out_of_stock": "Stok habis!",
        "cart.item_not_found": "Item tidak ditemukan.",
        "cart.product_not_found": "Produk tidak ditemukan.",
        # ── checkout ───────────────────────────────────────
        "checkout.title": "Checkout",
        "checkout.address_prompt": "Silakan ketik alamat pengiriman Anda:",
        "checkout.address_too_short": "Alamat terlalu pendek. Silakan ketik alamat lengkap Anda.",
        "checkout.address_invalid": "Silakan ketik alamat pengiriman Anda sebagai teks.",
        "checkout.review_title": "Konfirmasi Pesanan",
        "checkout.confirm_prompt": "Konfirmasi untuk melanjutkan ke pembayaran.",
        "checkout.cancelled": "Checkout dibatalkan.",
        "checkout.session_expired": "Sesi checkout kadaluarsa. Silakan coba lagi.",
        "checkout.cart_empty": "Keranjang Anda kosong.",
        "checkout.invoice_sent": "Invoice dikirim! Silakan lakukan pembayaran.",
        "checkout.invoice_failed": "Gagal mengirim invoice. Stok dikembalikan.",
        "checkout.coupon_prompt": "🎟️ Masukkan kode kupon (atau /skip untuk tanpa kupon):",
        "checkout.coupon_applied": "✅ Kupon diterapkan! Diskon {percent}%",
        "checkout.coupon_skipped": "Lanjutkan tanpa kupon.",
        # ── orders ──────────────────────────────────────────
        "orders.empty": "Anda belum memiliki pesanan.",
        "orders.title": "Pesanan Anda:",
        "orders.tap_to_view": "Ketuk pesanan untuk melihat detail.",
        "orders.cancelled": "Pesanan dibatalkan.",
        "orders.stock_returned": "Stok telah dikembalikan.",
        "orders.cannot_cancel": "Pesanan tidak dapat dibatalkan.",
        "orders.reorder_added": "ditambahkan kembali ke keranjang.",
        "orders.reorder_partial": "Beberapa produk tidak tersedia atau stok habis.",
        # ── payments ────────────────────────────────────────
        "payment.success": "Pembayaran Berhasil!",
        "payment.success_detail": "Pesanan #{order_id} telah dibayar.",
        "payment.failed": "Pembayaran Gagal",
        "payment.failed_reason": "Alasan: {reason}",
        # ── admin ───────────────────────────────────────────
        "admin.not_admin": "Anda bukan admin. Akses ditolak.",
        "admin.panel_title": "Panel Admin",
        "admin.select_action": "Pilih aksi di bawah:",
        # ── coupons ────────────────────────────────────────
        "coupon.not_found": "Kupon tidak ditemukan.",
        "coupon.disabled": "Kupon sudah dinonaktifkan.",
        "coupon.expired": "Kupon sudah kadaluarsa.",
        "coupon.exhausted": "Kupon sudah habis digunakan.",
        "coupon.invalid": "Kupon tidak valid.",
        "coupon.redeemed": "Kupon diterapkan! Diskon {percent}%",
        # ── common ──────────────────────────────────────────
        "common.back": "Kembali",
        "common.cancel": "Batal",
        "common.confirm": "Konfirmasi",
        "common.delete": "Hapus",
        "common.edit": "Edit",
        "common.yes": "Ya",
        "common.no": "Tidak",
    },
    "en": {
        # ── start ───────────────────────────────────────────
        "start.welcome": "Welcome to {shop_name}!",
        "start.help_header": "Available commands:",
        # ── catalog ────────────────────────────────────────
        "catalog.empty": "Catalog is empty — no categories yet.",
        "catalog.select_category": "Select a category:",
        "catalog.no_products": "No products in this category.",
        "catalog.out_of_stock": "Out of stock",
        # ── cart ────────────────────────────────────────────
        "cart.empty": "Your cart is empty.",
        "cart.start_shopping": "Type /catalog to start shopping!",
        "cart.title": "Your Cart:",
        "cart.total": "Total",
        "cart.updated": "Quantity updated.",
        "cart.added": "added to cart!",
        "cart.removed": "removed from cart.",
        "cart.cleared": "Cart cleared.",
        "cart.clear_confirm": "Are you sure you want to clear the cart?",
        "cart.insufficient_stock": "Insufficient stock!",
        "cart.out_of_stock": "Out of stock!",
        "cart.item_not_found": "Item not found.",
        "cart.product_not_found": "Product not found.",
        # ── checkout ───────────────────────────────────────
        "checkout.title": "Checkout",
        "checkout.address_prompt": "Please type your shipping address:",
        "checkout.address_too_short": "Address too short. Please type your full address.",
        "checkout.address_invalid": "Please type your shipping address as text.",
        "checkout.review_title": "Order Confirmation",
        "checkout.confirm_prompt": "Confirm to proceed to payment.",
        "checkout.cancelled": "Checkout cancelled.",
        "checkout.session_expired": "Checkout session expired. Please try again.",
        "checkout.cart_empty": "Your cart is empty.",
        "checkout.invoice_sent": "Invoice sent! Please proceed with payment.",
        "checkout.invoice_failed": "Failed to send invoice. Stock has been returned.",
        "checkout.coupon_prompt": "🎟️ Enter coupon code (or /skip for no coupon):",
        "checkout.coupon_applied": "✅ Coupon applied! {percent}% discount",
        "checkout.coupon_skipped": "Continuing without coupon.",
        # ── orders ──────────────────────────────────────────
        "orders.empty": "You have no orders yet.",
        "orders.title": "Your Orders:",
        "orders.tap_to_view": "Tap an order to view details.",
        "orders.cancelled": "Order cancelled.",
        "orders.stock_returned": "Stock has been returned.",
        "orders.cannot_cancel": "Order cannot be cancelled.",
        "orders.reorder_added": "added back to cart.",
        "orders.reorder_partial": "Some products are unavailable or out of stock.",
        # ── payments ────────────────────────────────────────
        "payment.success": "Payment Successful!",
        "payment.success_detail": "Order #{order_id} has been paid.",
        "payment.failed": "Payment Failed",
        "payment.failed_reason": "Reason: {reason}",
        # ── admin ───────────────────────────────────────────
        "admin.not_admin": "You are not an admin. Access denied.",
        "admin.panel_title": "Admin Panel",
        "admin.select_action": "Select an action below:",
        # ── coupons ────────────────────────────────────────
        "coupon.not_found": "Coupon not found.",
        "coupon.disabled": "Coupon has been disabled.",
        "coupon.expired": "Coupon has expired.",
        "coupon.exhausted": "Coupon usage limit reached.",
        "coupon.invalid": "Invalid coupon.",
        "coupon.redeemed": "Coupon applied! {percent}% discount",
        # ── common ──────────────────────────────────────────
        "common.back": "Back",
        "common.cancel": "Cancel",
        "common.confirm": "Confirm",
        "common.delete": "Delete",
        "common.edit": "Edit",
        "common.yes": "Yes",
        "common.no": "No",
    },
}


def t(key: str, lang: str | None = None, **kwargs: object) -> str:
    """Translate a message key to the user's language.

    Parameters
    ----------
    key : str
        Message key in ``<feature>.<message_id>`` format.
    lang : str | None
        ISO-639-1 language code.  Defaults to ``settings.LANGUAGE``.
    **kwargs
        Format parameters interpolated into the translated string.

    Returns
    -------
    str
        The translated (and formatted) string, or the key itself
        if no translation is found.
    """
    language = lang or settings.LANGUAGE
    lang_dict = _TRANSLATIONS.get(language, {})
    template = lang_dict.get(key)

    if template is None:
        # Fallback to default language
        default_dict = _TRANSLATIONS.get(settings.LANGUAGE, {})
        template = default_dict.get(key)

    if template is None:
        # No translation found — return the key itself as a last resort
        return key

    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError:
            return template

    return template


def available_languages() -> list[str]:
    """Return the list of available language codes."""
    return list(_TRANSLATIONS.keys())
