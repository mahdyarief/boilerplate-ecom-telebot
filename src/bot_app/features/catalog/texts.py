"""Message text builders — pure formatting helpers, no I/O.

Every function receives plain data and returns a formatted string.
These are intentionally trivial so the router layer stays thin.
"""

from __future__ import annotations

from ...shared.money import Money


def fmt_product_detail(
    name: str,
    price: Money,
    stock: int,
    description: str | None = None,
) -> str:
    """Build the product-detail message text."""
    if description:
        return (
            f"📦 {name}\n\n"
            f"{description}\n\n"
            f"💰 Harga: {price.format()}\n"
            f"📦 Stok: {stock}"
        )
    return (
        f"📦 {name}\n\n"
        f"💰 Harga: {price.format()}\n"
        f"📦 Stok: {stock}"
    )


def fmt_cart_item_line(name: str, qty: int, subtotal: Money) -> str:
    """Format a single cart line."""
    return f"• {name} x{qty} — {subtotal.format()}"


def fmt_cart_summary(
    lines: list[str],
    total: Money,
) -> str:
    """Build the full cart message text."""
    header = "🛒 Keranjang Anda:\n\n"
    body = "\n".join(lines)
    footer = f"\n\n💰 Total: {total.format()}"
    return header + body + footer


def fmt_products_list(products: list, currency: str) -> str:
    """Build the text listing for products under a category."""
    parts: list[str] = []
    for p in products:
        price = Money(p.price_smallest_unit, currency)
        stock_tag = " ⚠️Stok habis" if p.stock == 0 else ""
        parts.append(f"📦 {p.name} — {price.format()}{stock_tag}")
    return "\n".join(parts)
