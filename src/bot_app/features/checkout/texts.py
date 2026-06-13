"""Message text builders for the checkout flow — pure formatting, no I/O."""

from __future__ import annotations

from ...shared.money import Money


def fmt_checkout_review(
    items: list,
    total_smallest_unit: int,
    currency: str,
    shipping_address: str,
) -> str:
    """Build the checkout review message text.

    Parameters
    ----------
    items : list[OrderItem]
        Order line items.
    total_smallest_unit : int
        Grand total in smallest currency unit.
    currency : str
        ISO-4217 currency code.
    shipping_address : str
        The shipping address the user entered.
    """
    lines: list[str] = []
    for item in items:
        unit_price = Money(item.unit_price_smallest_unit, currency)
        subtotal = unit_price * item.quantity
        lines.append(f"  • {item.product_name} x{item.quantity} — {subtotal.format()}")

    total = Money(total_smallest_unit, currency)

    return (
        "📋 **Konfirmasi Pesanan**\n\n"
        + "\n".join(lines)
        + f"\n\n💰 Total: {total.format()}"
        + f"\n📦 Alamat pengiriman: {shipping_address}"
        + "\n\nKonfirmasi untuk melanjutkan ke pembayaran."
    )


def fmt_payment_success(order_id: int, total_smallest_unit: int, currency: str) -> str:
    """Build the payment-success confirmation message."""
    total = Money(total_smallest_unit, currency)
    return (
        f"✅ **Pembayaran Berhasil!**\n\n"
        f"Pesanan #{order_id} telah dibayar.\n"
        f"💰 Total: {total.format()}\n\n"
        f"Terima kasih telah berbelanja! 🎉\n"
        f"Gunakan /orders untuk melihat pesanan Anda."
    )


def fmt_payment_failed(reason: str) -> str:
    """Build a payment-failure message."""
    return (
        f"❌ **Pembayaran Gagal**\n\n"
        f"Alasan: {reason}\n\n"
        f"Stok telah dikembalikan. Silakan coba lagi."
    )


def fmt_checkout_coupon_prompt() -> str:
    """Build the coupon prompt message during checkout."""
    return (
        "🎟️ **Kupon Diskon**\n\n"
        "Masukkan kode kupon untuk mendapatkan diskon, "
        "atau lewati untuk lanjut tanpa kupon."
    )


def fmt_coupon_applied(percent: int, currency: str, discount_amount: int) -> str:
    """Build the coupon-applied confirmation."""
    discount = Money(discount_amount, currency)
    return (
        f"✅ **Kupon diterapkan!**\n\n"
        f"🎟️ Diskon: {percent}% (−{discount.format()})"
    )


def fmt_coupon_invalid(error_message: str) -> str:
    """Build the coupon-invalid message."""
    return f"❌ {error_message}"


def fmt_review_with_coupon(
    items: list,
    total_smallest_unit: int,
    currency: str,
    shipping_address: str,
    discount_percent: int = 0,
    discount_amount: int = 0,
) -> str:
    """Build the checkout review with optional coupon discount."""
    lines: list[str] = []
    for item in items:
        unit_price = Money(item.unit_price_smallest_unit, currency)
        subtotal = unit_price * item.quantity
        lines.append(f"  • {item.product_name} x{item.quantity} — {subtotal.format()}")

    total = Money(total_smallest_unit, currency)
    discount_line = ""
    if discount_percent > 0 and discount_amount > 0:
        discount_money = Money(discount_amount, currency)
        discount_line = f"\n🎟️ Diskon: {discount_percent}% (−{discount_money.format()})"

    return (
        "📋 **Konfirmasi Pesanan**\n\n"
        + "\n".join(lines)
        + discount_line
        + f"\n\n💰 Total: {total.format()}"
        + f"\n📦 Alamat pengiriman: {shipping_address}"
        + "\n\nKonfirmasi untuk melanjutkan ke pembayaran."
    )


def fmt_order_detail(
    order_id: int,
    status: str,
    items: list,
    total_smallest_unit: int,
    currency: str,
    shipping_address: str | None,
) -> str:
    """Build the order-detail message."""
    from ...core.constants import OrderStatus

    status_emoji = {
        OrderStatus.PENDING.value: "⏳",
        OrderStatus.AWAITING_PAYMENT.value: "💳",
        OrderStatus.PAID.value: "✅",
        OrderStatus.SHIPPED.value: "🚚",
        OrderStatus.DELIVERED.value: "📦",
        OrderStatus.CANCELLED.value: "❌",
    }
    emoji = status_emoji.get(status, "❓")

    lines: list[str] = []
    for item in items:
        unit_price = Money(item.unit_price_smallest_unit, currency)
        subtotal = unit_price * item.quantity
        lines.append(f"  • {item.product_name} x{item.quantity} — {subtotal.format()}")

    total = Money(total_smallest_unit, currency)

    parts = [
        f"📦 **Pesanan #{order_id}**\n",
        f"{emoji} Status: {status}",
        "",
        "\n".join(lines),
        f"\n💰 Total: {total.format()}",
    ]

    if shipping_address:
        parts.append(f"📦 Alamat: {shipping_address}")

    return "\n".join(parts)


def fmt_orders_list(orders: list, currency: str) -> str:
    """Build the orders list message."""
    if not orders:
        return "📭 Anda belum memiliki pesanan."

    from ...core.constants import OrderStatus

    status_emoji = {
        OrderStatus.PENDING.value: "⏳",
        OrderStatus.AWAITING_PAYMENT.value: "💳",
        OrderStatus.PAID.value: "✅",
        OrderStatus.SHIPPED.value: "🚚",
        OrderStatus.DELIVERED.value: "📦",
        OrderStatus.CANCELLED.value: "❌",
    }

    lines: list[str] = ["📋 **Pesanan Anda:**\n"]
    for order in orders:
        emoji = status_emoji.get(order.status, "❓")
        total = Money(order.total_smallest_unit, currency)
        lines.append(
            f"{emoji} #{order.id} — {total.format()} ({order.status})"
        )

    lines.append("\nKetuk pesanan untuk melihat detail.")
    return "\n".join(lines)


def fmt_qris_payment_instructions(
    order_id: int,
    final_amount: int,
    base_amount: int,
    unique_code: int,
    currency: str,
    provider: str,
    payment_url: str | None = None,
) -> str:
    """Build the QRIS / Pakasir payment instructions message.

    Parameters
    ----------
    order_id : int
        The order ID.
    final_amount : int
        Total amount to pay (base + unique code).
    base_amount : int
        Base order amount before unique code.
    unique_code : int
        Unique suffix for reconciliation.
    currency : str
        ISO-4217 currency code.
    provider : str
        Provider name ("qris" or "pakasir").
    payment_url : str | None
        Optional Pakasir payment page URL.
    """
    total = Money(final_amount, currency)
    base = Money(base_amount, currency)

    lines = [
        f"💳 **Pembayaran Pesanan #{order_id}**\n",
        f"💰 Total yang harus dibayar: **{total.format()}**",
        f"   (Harga pesanan: {base.format()} + Kode unik: {unique_code})",
        "",
        "📱 **Cara Bayar:**",
        "1. Scan QR code di bawah ini dengan aplikasi e-wallet / mobile banking Anda",
        "2. Pastikan nominal yang terisi sesuai dengan total di atas",
        "3. Setelah bayar, tekan tombol **Cek Pembayaran** di bawah",
    ]

    if payment_url:
        lines.append("")
        lines.append(f"🔗 Atau bayar via: {payment_url}")

    lines.append("")
    lines.append("⚠️ Pembayaran akan kadaluarsa dalam 15 menit.")

    return "\n".join(lines)


def fmt_pakasir_payment_instructions(
    order_id: int,
    final_amount: int,
    currency: str,
    payment_url: str,
) -> str:
    """Build the Pakasir-specific payment instructions message.

    Parameters
    ----------
    order_id : int
        The order ID.
    final_amount : int
        Total amount to pay.
    currency : str
        ISO-4217 currency code.
    payment_url : str
        Pakasir payment page URL.
    """
    total = Money(final_amount, currency)

    lines = [
        f"💳 **Pembayaran Pesanan #{order_id}**\n",
        f"💰 Total yang harus dibayar: **{total.format()}**",
        "",
        "📱 **Cara Bayar:**",
        f"1. Buka halaman pembayaran: {payment_url}",
        "2. Pilih metode pembayaran yang Anda inginkan",
        "3. Selesaikan pembayaran",
        "4. Setelah bayar, tekan tombol **Cek Pembayaran** di bawah",
        "",
        "⚠️ Pembayaran akan kadaluarsa dalam 15 menit.",
    ]

    return "\n".join(lines)


def fmt_payment_check_paid(order_id: int, total_smallest_unit: int, currency: str) -> str:
    """Build message when payment check detects the order is paid."""
    total = Money(total_smallest_unit, currency)
    return (
        f"✅ **Pembayaran Diterima!**\n\n"
        f"Pesanan #{order_id} telah dibayar.\n"
        f"💰 Total: {total.format()}\n\n"
        f"Terima kasih telah berbelanja! 🎉\n"
        f"Gunakan /orders untuk melihat pesanan Anda."
    )


def fmt_payment_check_pending() -> str:
    """Build message when payment check shows still pending."""
    return (
        "⏳ **Pembayaran Belum Diterima**\n\n"
        "Kami belum menerima pembayaran Anda. "
        "Pastikan nominal yang Anda bayarkan sesuai dengan total "
        "(termasuk kode unik).\n\n"
        "Jika Anda sudah bayar, tunggu 1-2 menit lalu cek lagi."
    )


def fmt_payment_cancelled(order_id: int) -> str:
    """Build message when a pending payment is cancelled by the user."""
    return (
        f"❌ **Pembayaran Dibatalkan**\n\n"
        f"Pesanan #{order_id} telah dibatalkan dan stok dikembalikan.\n"
        f"Ketik /cart untuk melihat keranjang Anda."
    )
