"""Message text builders for the admin surface — pure formatting, no I/O."""

from __future__ import annotations

from ...core.constants import OrderStatus
from ...shared.money import Money


def fmt_admin_panel() -> str:
    """Build the admin panel landing text."""
    return (
        "🔧 **Panel Admin**\n\n"
        "Pilih aksi di bawah:"
    )


def fmt_admin_menu_help() -> str:
    """Build the admin command help text."""
    return (
        "🔧 **Perintah Admin:**\n\n"
        "/admin — Buka panel admin\n\n"
        "Semua aksi dilakukan melalui tombol inline di panel admin."
    )


def fmt_not_admin() -> str:
    """Build the 'not an admin' error message."""
    return "⛔ Anda bukan admin. Akses ditolak."


# ── Category texts ────────────────────────────────────────


def fmt_category_list(
    categories: list,
    *,
    include_inactive: bool = False,
) -> str:
    """Build the admin category list text."""
    if not categories:
        return "📂 **Kategori**\n\n📭 Belum ada kategori."

    lines = ["📂 **Kategori:**\n"]
    for cat in categories:
        status = "✅" if cat.is_active else "❌"
        parent = f" (parent: {cat.parent_id})" if cat.parent_id else ""
        lines.append(
            f"  {status} #{cat.id} {cat.name} [{cat.slug}]{parent}"
        )
        if include_inactive and cat.children:
            for child in cat.children:
                child_status = "✅" if child.is_active else "❌"
                lines.append(
                    f"    {child_status} #{child.id} {child.name} [{child.slug}]"
                )

    return "\n".join(lines)


def fmt_category_detail(category: object) -> str:
    """Build the admin category detail text."""
    status = "✅ Aktif" if category.is_active else "❌ Nonaktif"
    parent = f"\n📂 Parent: #{category.parent_id}" if category.parent_id else ""

    children_lines = ""
    if category.children:
        lines = []
        for child in category.children:
            child_status = "✅" if child.is_active else "❌"
            lines.append(f"  {child_status} #{child.id} {child.name}")
        children_lines = "\n📂 Sub-kategori:\n" + "\n".join(lines)

    product_count = len(category.products) if category.products else 0

    return (
        f"📂 **Kategori #{category.id}**\n\n"
        f"Nama: {category.name}\n"
        f"Slug: {category.slug}\n"
        f"Posisi: {category.position}\n"
        f"Status: {status}\n"
        f"Jumlah produk: {product_count}"
        f"{parent}"
        f"{children_lines}"
    )


def fmt_category_created(category: object) -> str:
    """Build the category-created confirmation."""
    return (
        f"✅ **Kategori dibuat!**\n\n"
        f"📦 #{category.id} {category.name} [{category.slug}]"
    )


def fmt_category_updated(category: object) -> str:
    """Build the category-updated confirmation."""
    return f"✅ Kategori #{category.id} diperbarui."


def fmt_ask_category_name() -> str:
    """Ask admin for category name."""
    return "📝 Ketik nama kategori baru:"


def fmt_ask_category_slug() -> str:
    """Ask admin for category slug."""
    return "📝 Ketik slug kategori (huruf kecil, tanpa spasi, contoh: elektronik):"


def fmt_ask_category_edit_value(field: str, current_value: str) -> str:
    """Ask admin for a new category field value."""
    return f"📝 Mengubah **{field}** (saat ini: {current_value})\n\nKetik nilai baru:"


# ── Product texts ────────────────────────────────────────


def fmt_product_list(
    products: list,
    *,
    currency: str = "IDR",
) -> str:
    """Build the admin product list text."""
    if not products:
        return "📦 **Produk**\n\n📭 Belum ada produk."

    lines = ["📦 **Produk:**\n"]
    for p in products:
        status = "✅" if p.is_active else "❌"
        price = Money(p.price_smallest_unit, currency)
        lines.append(
            f"  {status} #{p.id} {p.name} — {price.format()} (stok: {p.stock})"
        )

    return "\n".join(lines)


def fmt_product_detail(product: object, *, currency: str = "IDR") -> str:
    """Build the admin product detail text."""
    status = "✅ Aktif" if product.is_active else "❌ Nonaktif"
    price = Money(product.price_smallest_unit, currency)
    desc = product.description or "—"

    return (
        f"📦 **Produk #{product.id}**\n\n"
        f"Nama: {product.name}\n"
        f"Kategori: #{product.category_id}\n"
        f"Harga: {price.format()}\n"
        f"Stok: {product.stock}\n"
        f"Deskripsi: {desc}\n"
        f"Status: {status}"
    )


def fmt_product_created(product: object, *, currency: str = "IDR") -> str:
    """Build the product-created confirmation."""
    price = Money(product.price_smallest_unit, currency)
    return (
        f"✅ **Produk dibuat!**\n\n"
        f"📦 #{product.id} {product.name} — {price.format()} (stok: {product.stock})"
    )


def fmt_product_updated(product: object) -> str:
    """Build the product-updated confirmation."""
    return f"✅ Produk #{product.id} diperbarui."


def fmt_ask_product_name() -> str:
    """Ask admin for product name."""
    return "📝 Ketik nama produk baru:"


def fmt_ask_product_price() -> str:
    """Ask admin for product price."""
    return "📝 Ketik harga produk (angka saja, tanpa titik/koma, contoh: 50000):"


def fmt_ask_product_stock() -> str:
    """Ask admin for product stock."""
    return "📝 Ketik jumlah stok produk (angka saja, contoh: 100):"


def fmt_ask_product_description() -> str:
    """Ask admin for product description."""
    return "📝 Ketik deskripsi produk (atau /skip untuklewati):"


def fmt_ask_product_edit_value(field: str, current_value: str) -> str:
    """Ask admin for a new product field value."""
    return f"📝 Mengubah **{field}** (saat ini: {current_value})\n\nKetik nilai baru:"


def fmt_ask_select_category() -> str:
    """Ask admin to select a category for the new product."""
    return "📂 Pilih kategori untuk produk baru:"


# ── Order management texts ───────────────────────────────


def fmt_admin_order_list(orders: list, *, currency: str = "IDR") -> str:
    """Build the admin order list text."""
    if not orders:
        return "📋 **Pesanan**\n\n📭 Belum ada pesanan."

    status_emoji = {
        OrderStatus.PENDING.value: "⏳",
        OrderStatus.AWAITING_PAYMENT.value: "💳",
        OrderStatus.PAID.value: "✅",
        OrderStatus.SHIPPED.value: "🚚",
        OrderStatus.DELIVERED.value: "📦",
        OrderStatus.CANCELLED.value: "❌",
    }

    lines = ["📋 **Pesanan:**\n"]
    for o in orders:
        emoji = status_emoji.get(o.status, "❓")
        total = Money(o.total_smallest_unit, currency)
        lines.append(
            f"  {emoji} #{o.id} — {total.format()} ({o.status}) user:{o.user_id}"
        )

    return "\n".join(lines)


def fmt_admin_order_detail(order: object, items: list, *, currency: str = "IDR") -> str:
    """Build the admin order detail text."""
    status_emoji = {
        OrderStatus.PENDING.value: "⏳",
        OrderStatus.AWAITING_PAYMENT.value: "💳",
        OrderStatus.PAID.value: "✅",
        OrderStatus.SHIPPED.value: "🚚",
        OrderStatus.DELIVERED.value: "📦",
        OrderStatus.CANCELLED.value: "❌",
    }
    emoji = status_emoji.get(order.status, "❓")
    total = Money(order.total_smallest_unit, currency)
    address = order.shipping_address or "—"

    item_lines: list[str] = []
    for item in items:
        unit_price = Money(item.unit_price_smallest_unit, currency)
        subtotal = unit_price * item.quantity
        item_lines.append(f"  • {item.product_name} x{item.quantity} — {subtotal.format()}")

    return (
        f"📋 **Pesanan #{order.id}**\n\n"
        f"{emoji} Status: {order.status}\n"
        f"👤 User: {order.user_id}\n"
        f"💰 Total: {total.format()}\n"
        f"📦 Alamat: {address}\n\n"
        + "\n".join(item_lines)
    )


def fmt_order_status_updated(order_id: int, new_status: str) -> str:
    """Build the order-status-updated confirmation."""
    return f"✅ Pesanan #{order_id} status diperbarui ke **{new_status}**."


# ── Broadcast texts ──────────────────────────────────────


def fmt_ask_broadcast_message() -> str:
    """Ask admin for the broadcast message."""
    return (
        "📢 **Broadcast**\n\n"
        "Ketik atau forward pesan yang ingin dikirim ke semua pengguna.\n\n"
        "Pesan akan dikirim apa adanya (teks saja)."
    )


def fmt_broadcast_preview(recipient_count: int, text: str) -> str:
    """Build the broadcast preview/confirmation text."""
    return (
        f"📢 **Preview Broadcast**\n\n"
        f"Penerima: {recipient_count} pengguna\n\n"
        f"Pesan:\n{text}\n\n"
        f"Konfirmasi untuk mengirim."
    )


def fmt_broadcast_sent(success: int, failed: int) -> str:
    """Build the broadcast-completed confirmation."""
    return (
        f"📢 **Broadcast selesai!**\n\n"
        f"✅ Berhasil: {success}\n"
        f"❌ Gagal: {failed}"
    )


def fmt_broadcast_cancelled() -> str:
    """Build the broadcast-cancelled message."""
    return "❌ Broadcast dibatalkan."


# ── Coupon texts ────────────────────────────────────────


def fmt_coupon_list(coupons: list) -> str:
    """Build the admin coupon list text."""
    if not coupons:
        return "🎟️ **Kupon**\n\n📭 Belum ada kupon."

    lines = ["🎟️ **Kupon:**\n"]
    for c in coupons:
        status = "✅" if c.is_active else "❌"
        uses_display = f"{c.used_count}/{c.max_uses}" if c.max_uses else str(c.used_count)
        expires = ""
        if c.expires_at:
            expires = f" (s/d {c.expires_at.strftime('%Y-%m-%d %H:%M')})"
        lines.append(f"  {status} #{c.id} {c.code} — {c.discount_percent}% (digunakan: {uses_display}){expires}")

    return "\n".join(lines)


def fmt_coupon_detail(coupon: object) -> str:
    """Build the admin coupon detail text."""
    status = "✅ Aktif" if coupon.is_active else "❌ Nonaktif"
    uses_display = f"{coupon.used_count}/{coupon.max_uses}" if coupon.max_uses else str(coupon.used_count)
    expires = coupon.expires_at.strftime("%Y-%m-%d %H:%M UTC") if coupon.expires_at else "Tidak ada"

    return (
        f"🎟️ **Kupon #{coupon.id}**\n\n"
        f"Kode: `{coupon.code}`\n"
        f"Diskon: {coupon.discount_percent}%\n"
        f"Digunakan: {uses_display}\n"
        f"Kadaluarsa: {expires}\n"
        f"Status: {status}"
    )


def fmt_coupon_created(coupon: object) -> str:
    """Build the coupon-created confirmation."""
    return (
        f"✅ **Kupon dibuat!**\n\n"
        f"🎟️ #{coupon.id} `{coupon.code}` — {coupon.discount_percent}%"
    )


def fmt_ask_coupon_code() -> str:
    """Ask admin for coupon code."""
    return "📝 Ketik kode kupon (contoh: DISKON50):"


def fmt_ask_coupon_discount() -> str:
    """Ask admin for coupon discount percentage."""
    return "📝 Ketik persentase diskon (1-100, contoh: 25):"


def fmt_ask_coupon_max_uses() -> str:
    """Ask admin for max uses."""
    return "📝 Ketik jumlah maksimal penggunaan (atau /skip untuk tanpa batas):"


def fmt_ask_coupon_expires() -> str:
    """Ask admin for expiry date."""
    return "📝 Ketik tanggal kadaluarsa (format: YYYY-MM-DD, atau /skip untuk tanpa batas):"


# ── Product image texts ──────────────────────────────────


def fmt_product_images(product: object, images: list) -> str:
    """Build the admin product images text."""
    count_text = f"{len(images)} gambar" if images else "belum ada gambar"

    lines = [
        f"🖼️ **Gambar Produk #{product.id} — {product.name}**\n",
        f"Total: {count_text}\n",
    ]
    if images:
        for img in images:
            cover_flag = "⭐ Cover" if img.is_cover else ""
            lines.append(f"  #{img.id} pos:{img.position} {cover_flag}")
        lines.append("\nKirim foto untuk menambahkan gambar baru.")
    else:
        lines.append("Kirim foto untuk menambahkan gambar pertama.")

    return "\n".join(lines)


def fmt_product_image_added(image: object) -> str:
    """Build the product image added confirmation."""
    cover = " (⭐ Cover)" if image.is_cover else ""
    return f"✅ Gambar #{image.id} ditambahkan{cover}."


def fmt_product_image_cover_set(image_id: int) -> str:
    """Build the product image cover set confirmation."""
    return f"⭐ Gambar #{image_id} dijadikan cover."


def fmt_product_image_deleted(image_id: int) -> str:
    """Build the product image deleted confirmation."""
    return f"🗑️ Gambar #{image_id} dihapus."
