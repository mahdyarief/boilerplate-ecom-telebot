"""Tests for catalog text builder helpers."""

from __future__ import annotations

from types import SimpleNamespace

from bot_app.features.catalog.texts import (
    fmt_cart_item_line,
    fmt_cart_summary,
    fmt_product_detail,
    fmt_products_list,
)
from bot_app.shared.money import Money


class TestFmtProductDetail:
    def test_with_description(self) -> None:
        price = Money(50000, "IDR")
        text = fmt_product_detail("Widget", price, stock=10, description="Great widget")
        assert "📦 Widget" in text
        assert "Great widget" in text
        assert "Rp 50.000" in text
        assert "Stok: 10" in text

    def test_without_description(self) -> None:
        price = Money(25000, "IDR")
        text = fmt_product_detail("Gadget", price, stock=5)
        assert "📦 Gadget" in text
        assert "Rp 25.000" in text
        # No description block
        assert text.count("\n\n") == 1

    def test_zero_stock(self) -> None:
        price = Money(10000, "IDR")
        text = fmt_product_detail("Sold Out", price, stock=0)
        assert "Stok: 0" in text


class TestFmtCartItemLine:
    def test_basic(self) -> None:
        subtotal = Money(100000, "IDR")
        line = fmt_cart_item_line("Widget", qty=2, subtotal=subtotal)
        assert "Widget" in line
        assert "x2" in line
        assert "Rp 100.000" in line

    def test_quantity_one(self) -> None:
        subtotal = Money(50000, "IDR")
        line = fmt_cart_item_line("Item", qty=1, subtotal=subtotal)
        assert "x1" in line


class TestFmtCartSummary:
    def test_basic(self) -> None:
        lines = ["• Widget ×2 — Rp 100.000", "• Gadget ×1 — Rp 25.000"]
        total = Money(125000, "IDR")
        text = fmt_cart_summary(lines, total)
        assert "🛒 Keranjang Anda:" in text
        assert "• Widget ×2" in text
        assert "• Gadget ×1" in text
        assert "Total: Rp 125.000" in text

    def test_empty_lines(self) -> None:
        total = Money.zero("IDR")
        text = fmt_cart_summary([], total)
        assert "🛒 Keranjang Anda:" in text
        assert "Total: Rp 0" in text


class TestFmtProductsList:
    def test_basic(self) -> None:
        p1 = SimpleNamespace(name="A", price_smallest_unit=10000, stock=5)
        p2 = SimpleNamespace(name="B", price_smallest_unit=20000, stock=0)
        text = fmt_products_list([p1, p2], "IDR")
        assert "📦 A — Rp 10.000" in text
        assert "📦 B — Rp 20.000" in text
        assert "⚠️Stok habis" in text  # out of stock tag

    def test_all_in_stock(self) -> None:
        p = SimpleNamespace(name="X", price_smallest_unit=5000, stock=100)
        text = fmt_products_list([p], "IDR")
        assert "⚠️" not in text
