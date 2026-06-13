"""Message text builders — pure formatting helpers, no I/O.

Every function receives plain data and returns a formatted string.
These are intentionally trivial so the router layer stays thin.
"""

from __future__ import annotations

from ...infrastructure.i18n.translations import t
from ...shared.money import Money


def fmt_product_detail(
    name: str,
    price: Money,
    stock: int,
    description: str | None = None,
    *,
    lang: str = "id",
) -> str:
    """Build the product-detail message text."""
    if description:
        return t("catalog.product_detail", lang, name=name, description=description, price=price.format(), stock=stock)
    return t("catalog.product_no_desc", lang, name=name, price=price.format(), stock=stock)


def fmt_cart_item_line(name: str, qty: int, subtotal: Money) -> str:
    """Format a single cart line."""
    return f"• {name} x{qty} — {subtotal.format()}"


def fmt_cart_summary(
    lines: list[str],
    total: Money,
    *,
    lang: str = "id",
) -> str:
    """Build the full cart message text."""
    header = t("cart.header", lang)
    body = "\n".join(lines)
    footer = f"\n\n{t('cart.total_with_value', lang, total=total.format())}"
    return header + body + footer


def fmt_products_list(products: list, currency: str, *, lang: str = "id") -> str:
    """Build the text listing for products under a category."""
    parts: list[str] = []
    for p in products:
        price = Money(p.price_smallest_unit, currency)
        stock_tag = f" ⚠️{t('catalog.out_of_stock', lang)}" if p.stock == 0 else ""
        parts.append(f"📦 {p.name} — {price.format()}{stock_tag}")
    return "\n".join(parts)
