"""Tests for checkout text builders and order text formatters."""

from __future__ import annotations

from types import SimpleNamespace

from bot_app.core.constants import OrderStatus
from bot_app.features.checkout.texts import (
    fmt_checkout_review,
    fmt_order_detail,
    fmt_orders_list,
    fmt_payment_failed,
    fmt_payment_success,
)


def _make_order_item(name: str, qty: int, unit_price: int) -> SimpleNamespace:
    return SimpleNamespace(
        product_name=name,
        quantity=qty,
        unit_price_smallest_unit=unit_price,
    )


# ── fmt_checkout_review ──────────────────────────────────


class TestFmtCheckoutReview:
    def test_single_item(self) -> None:
        items = [_make_order_item("Widget", 2, 50000)]
        text = fmt_checkout_review(items, 100000, "IDR", "Jl. Test")
        assert "Widget" in text
        assert "x2" in text
        assert "Total" in text or "Rp" in text
        assert "Jl. Test" in text

    def test_multiple_items(self) -> None:
        items = [
            _make_order_item("A", 1, 10000),
            _make_order_item("B", 3, 20000),
        ]
        text = fmt_checkout_review(items, 70000, "IDR", "Home")
        assert "A" in text
        assert "B" in text
        assert "x1" in text
        assert "x3" in text


# ── fmt_payment_success ──────────────────────────────────


class TestFmtPaymentSuccess:
    def test_format(self) -> None:
        text = fmt_payment_success(123, 50000, "IDR")
        assert "#123" in text
        assert "Berhasil" in text


# ── fmt_payment_failed ────────────────────────────────────


class TestFmtPaymentFailed:
    def test_format(self) -> None:
        text = fmt_payment_failed("Insufficient funds")
        assert "Gagal" in text
        assert "Insufficient funds" in text


# ── fmt_order_detail ─────────────────────────────────────


class TestFmtOrderDetail:
    def test_paid_order(self) -> None:
        items = [_make_order_item("Widget", 1, 50000)]
        text = fmt_order_detail(1, OrderStatus.PAID.value, items, 50000, "IDR", "Addr")
        assert "#1" in text
        assert "paid" in text.lower() or "✅" in text
        assert "Widget" in text
        assert "Addr" in text

    def test_cancelled_order(self) -> None:
        items = [_make_order_item("Widget", 1, 50000)]
        text = fmt_order_detail(2, OrderStatus.CANCELLED.value, items, 50000, "IDR", None)
        assert "#2" in text
        assert "cancel" in text.lower() or "❌" in text

    def test_no_shipping_address(self) -> None:
        items = [_make_order_item("Widget", 1, 50000)]
        text = fmt_order_detail(3, OrderStatus.PENDING.value, items, 50000, "IDR", None)
        assert "Alamat" not in text


# ── fmt_orders_list ──────────────────────────────────────


class TestFmtOrdersList:
    def test_empty(self) -> None:
        text = fmt_orders_list([], "IDR")
        assert "belum memiliki" in text

    def test_with_orders(self) -> None:
        orders = [
            SimpleNamespace(id=1, total_smallest_unit=50000, status="paid"),
            SimpleNamespace(id=2, total_smallest_unit=30000, status="cancelled"),
        ]
        text = fmt_orders_list(orders, "IDR")
        assert "#1" in text
        assert "#2" in text
        assert "paid" in text or "✅" in text
