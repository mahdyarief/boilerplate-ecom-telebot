"""Pricing calculations — pure functions, no side effects, no I/O.

Every function here is total: invalid input raises ``ValueError`` with a
clear message.  Use this module from checkout / cart / admin services.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...shared.money import Money


@dataclass(frozen=True, slots=True)
class LineItem:
    """A priced line in a cart or order (pre-tax, pre-discount)."""

    unit_price: Money
    quantity: int


@dataclass(frozen=True, slots=True)
class PriceBreakdown:
    """Subtotal → discount → total.  Invariant: subtotal - discount == total."""

    subtotal: Money
    discount: Money
    total: Money


# ── public API ──────────────────────────────────────────────


def compute_subtotal(items: list[LineItem], currency: str) -> Money:
    """Sum of (unit_price * quantity) for all items.  All items must share the currency."""
    if not items:
        return Money.zero(currency)
    total = Money.zero(currency)
    for item in items:
        if not isinstance(item.quantity, int) or isinstance(item.quantity, bool):
            raise ValueError(f"quantity must be int, got {type(item.quantity).__name__}")
        if item.quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {item.quantity}")
        if item.unit_price.currency != currency:
            raise ValueError(
                f"line item currency {item.unit_price.currency!r} != expected {currency!r}"
            )
        total = total + (item.unit_price * item.quantity)
    return total


def apply_percentage_discount(subtotal: Money, percent: int) -> Money:
    """Return a discount Money of ``percent``% of ``subtotal`` (integer percent, 0-100).

    Uses bankers-friendly rounding: ``int(round(x))`` so 33% of 100 = 33,
    50% of 99 = 50 (rounds half-to-even on .5 boundaries).
    """
    if not isinstance(percent, int) or isinstance(percent, bool):
        raise ValueError(f"percent must be int, got {type(percent).__name__}")
    if not 0 <= percent <= 100:
        raise ValueError(f"percent must be in [0, 100], got {percent}")
    if subtotal.is_zero():
        return Money.zero(subtotal.currency)
    discount_minor = round(subtotal.amount_minor * percent / 100)
    # Never discount more than the subtotal
    discount_minor = min(discount_minor, subtotal.amount_minor)
    return Money(discount_minor, subtotal.currency)


def apply_coupon_discount(subtotal: Money, coupon_percent: int) -> Money:
    """Apply a coupon discount to the subtotal.

    Semantically identical to :func:`apply_percentage_discount` but
    exists as a named entry point so the checkout flow can distinguish
    between a general discount and a coupon-based one.

    Parameters
    ----------
    subtotal : Money
        The pre-discount subtotal.
    coupon_percent : int
        The coupon's discount percentage (1-100).

    Returns
    -------
    Money
        The discount amount (always ≤ subtotal).
    """
    return apply_percentage_discount(subtotal, coupon_percent)


def compute_total(
    items: list[LineItem],
    currency: str,
    discount_percent: int = 0,
    coupon_percent: int = 0,
) -> PriceBreakdown:
    """Subtotal → discount → coupon → total.  Returns a ``PriceBreakdown``.

    Parameters
    ----------
    discount_percent : int
        General discount percentage (0-100).
    coupon_percent : int
        Additional coupon discount percentage (0-100), applied after
        the general discount.
    """
    subtotal = compute_subtotal(items, currency)
    discount = apply_percentage_discount(subtotal, discount_percent)
    after_general = subtotal - discount
    coupon_discount = apply_coupon_discount(after_general, coupon_percent)
    total = after_general - coupon_discount
    # Combine discounts for the breakdown
    combined_discount = discount + coupon_discount
    return PriceBreakdown(subtotal=subtotal, discount=combined_discount, total=total)
