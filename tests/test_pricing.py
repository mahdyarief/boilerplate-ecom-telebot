"""Tests for the pricing service — pure functions, no DB."""

from __future__ import annotations

import pytest

from bot_app.app.services.pricing import (
    LineItem,
    PriceBreakdown,
    apply_percentage_discount,
    compute_subtotal,
    compute_total,
)
from bot_app.shared.money import Money


def item(unit_minor: int, qty: int = 1) -> LineItem:
    return LineItem(unit_price=Money(unit_minor, "IDR"), quantity=qty)


# ── compute_subtotal ────────────────────────────────────────


class TestComputeSubtotal:
    def test_empty(self) -> None:
        assert compute_subtotal([], "IDR") == Money.zero("IDR")

    def test_single(self) -> None:
        assert compute_subtotal([item(1000)], "IDR") == Money(1000, "IDR")

    def test_multiple(self) -> None:
        assert compute_subtotal([item(1000), item(2500, 2), item(500, 3)], "IDR") == Money(
            1000 + 2500 * 2 + 500 * 3, "IDR"
        )

    def test_quantity_multiplies(self) -> None:
        assert compute_subtotal([item(1000, 5)], "IDR") == Money(5000, "IDR")

    def test_rejects_zero_quantity(self) -> None:
        with pytest.raises(ValueError, match="quantity must be > 0"):
            compute_subtotal([item(1000, 0)], "IDR")

    def test_rejects_negative_quantity(self) -> None:
        with pytest.raises(ValueError, match="quantity must be > 0"):
            compute_subtotal([item(1000, -1)], "IDR")

    def test_rejects_non_int_quantity(self) -> None:
        with pytest.raises(ValueError, match="quantity must be int"):
            compute_subtotal([LineItem(Money(1000, "IDR"), 1.5)], "IDR")  # type: ignore[arg-type]

    def test_rejects_currency_mismatch(self) -> None:
        items = [LineItem(Money(1000, "IDR"), 1), LineItem(Money(1000, "USD"), 1)]
        with pytest.raises(ValueError, match="line item currency"):
            compute_subtotal(items, "IDR")


# ── apply_percentage_discount ───────────────────────────────


class TestApplyPercentageDiscount:
    def test_zero_percent(self) -> None:
        m = Money(10000, "IDR")
        assert apply_percentage_discount(m, 0) == Money.zero("IDR")

    def test_hundred_percent(self) -> None:
        m = Money(10000, "IDR")
        assert apply_percentage_discount(m, 100) == Money(10000, "IDR")

    def test_fifty_percent(self) -> None:
        m = Money(10000, "IDR")
        assert apply_percentage_discount(m, 50) == Money(5000, "IDR")

    def test_third(self) -> None:
        m = Money(10000, "IDR")
        assert apply_percentage_discount(m, 33) == Money(3300, "IDR")  # 3300.0 → int 3300

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="percent must be in"):
            apply_percentage_discount(Money(10000, "IDR"), -1)

    def test_rejects_over_hundred(self) -> None:
        with pytest.raises(ValueError, match="percent must be in"):
            apply_percentage_discount(Money(10000, "IDR"), 101)

    def test_rejects_non_int(self) -> None:
        with pytest.raises(ValueError, match="percent must be int"):
            apply_percentage_discount(Money(10000, "IDR"), 10.5)  # type: ignore[arg-type]

    def test_zero_subtotal_yields_zero_discount(self) -> None:
        assert apply_percentage_discount(Money.zero("IDR"), 50) == Money.zero("IDR")

    def test_never_exceeds_subtotal(self) -> None:
        # edge case: rounding could push 100% discount of 99 to 100, but we clamp
        assert apply_percentage_discount(Money(99, "IDR"), 100) == Money(99, "IDR")


# ── compute_total ───────────────────────────────────────────


class TestComputeTotal:
    def test_no_discount(self) -> None:
        items = [item(1000, 2), item(500, 3)]
        breakdown = compute_total(items, "IDR")
        assert breakdown.subtotal == Money(3500, "IDR")
        assert breakdown.discount == Money.zero("IDR")
        assert breakdown.total == Money(3500, "IDR")

    def test_with_discount(self) -> None:
        items = [item(10000, 1)]
        breakdown = compute_total(items, "IDR", discount_percent=10)
        assert breakdown.subtotal == Money(10000, "IDR")
        assert breakdown.discount == Money(1000, "IDR")
        assert breakdown.total == Money(9000, "IDR")

    def test_invariant_subtotal_minus_discount_equals_total(self) -> None:
        items = [item(3333, 3), item(7777, 2)]
        breakdown = compute_total(items, "IDR", discount_percent=15)
        assert breakdown.subtotal - breakdown.discount == breakdown.total

    def test_empty_cart(self) -> None:
        breakdown = compute_total([], "IDR", discount_percent=20)
        assert breakdown.subtotal == Money.zero("IDR")
        assert breakdown.discount == Money.zero("IDR")
        assert breakdown.total == Money.zero("IDR")

    def test_pricebreakdown_is_frozen(self) -> None:
        b = compute_total([item(1000)], "IDR")
        with pytest.raises((AttributeError, Exception)):
            b.subtotal = Money(9999, "IDR")  # type: ignore[misc]
