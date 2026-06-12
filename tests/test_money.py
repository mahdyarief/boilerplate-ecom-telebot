"""Tests for the Money value object."""

from __future__ import annotations

import pytest

from bot_app.shared.money import Money


# ── construction ────────────────────────────────────────────


class TestConstruction:
    def test_basic(self) -> None:
        m = Money(15000, "IDR")
        assert m.amount_minor == 15000
        assert m.currency == "IDR"

    def test_currency_normalised_to_uppercase(self) -> None:
        assert Money(100, "idr").currency == "IDR"
        assert Money(100, "usd").currency == "USD"

    def test_zero(self) -> None:
        m = Money.zero("IDR")
        assert m.amount_minor == 0
        assert m.currency == "IDR"
        assert m.is_zero()

    def test_rejects_non_int_amount(self) -> None:
        with pytest.raises(TypeError):
            Money(15.5, "IDR")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            Money("15000", "IDR")  # type: ignore[arg-type]

    def test_rejects_bool_amount(self) -> None:
        with pytest.raises(TypeError):
            Money(True, "IDR")  # type: ignore[arg-type]

    def test_rejects_bad_currency(self) -> None:
        with pytest.raises(ValueError):
            Money(100, "ID")  # too short
        with pytest.raises(ValueError):
            Money(100, "IDRR")  # too long
        with pytest.raises(ValueError):
            Money(100, "12")  # not alpha
        with pytest.raises(ValueError):
            Money(100, "")  # empty


# ── arithmetic ──────────────────────────────────────────────


class TestArithmetic:
    def test_add_same_currency(self) -> None:
        a = Money(1000, "IDR")
        b = Money(500, "IDR")
        assert a + b == Money(1500, "IDR")

    def test_sub_same_currency(self) -> None:
        a = Money(1000, "IDR")
        b = Money(300, "IDR")
        assert a - b == Money(700, "IDR")

    def test_mul_int(self) -> None:
        m = Money(1000, "IDR")
        assert m * 3 == Money(3000, "IDR")
        assert 3 * m == Money(3000, "IDR")  # type: ignore[operator]

    def test_add_currency_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="currency mismatch"):
            Money(100, "IDR") + Money(100, "USD")

    def test_sub_currency_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="currency mismatch"):
            Money(100, "IDR") - Money(100, "USD")

    def test_mul_rejects_float(self) -> None:
        with pytest.raises(TypeError):
            Money(100, "IDR") * 1.5  # type: ignore[operator]

    def test_mul_rejects_bool(self) -> None:
        with pytest.raises(TypeError):
            Money(100, "IDR") * True  # type: ignore[operator]

    def test_sub_can_go_negative(self) -> None:
        # No clamping; callers decide if negative totals are valid
        assert Money(100, "IDR") - Money(200, "IDR") == Money(-100, "IDR")


# ── comparison ──────────────────────────────────────────────


class TestComparison:
    def test_lt(self) -> None:
        assert Money(100, "IDR") < Money(200, "IDR")
        assert not (Money(200, "IDR") < Money(100, "IDR"))

    def test_le(self) -> None:
        assert Money(100, "IDR") <= Money(100, "IDR")
        assert Money(100, "IDR") <= Money(200, "IDR")

    def test_gt(self) -> None:
        assert Money(200, "IDR") > Money(100, "IDR")

    def test_ge(self) -> None:
        assert Money(200, "IDR") >= Money(200, "IDR")

    def test_eq_with_non_money(self) -> None:
        assert Money(100, "IDR") != 100  # type: ignore[comparison-overlap]
        assert Money(100, "IDR") != "100 IDR"

    def test_comparison_currency_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="currency mismatch"):
            Money(100, "IDR") < Money(100, "USD")

    def test_hash_consistency(self) -> None:
        # equal Money objects must hash equal (frozen dataclass invariant)
        a = Money(100, "IDR")
        b = Money(100, "IDR")
        assert hash(a) == hash(b)
        assert {a, b} == {Money(100, "IDR")}


# ── helpers ─────────────────────────────────────────────────


class TestHelpers:
    def test_is_zero(self) -> None:
        assert Money(0, "IDR").is_zero()
        assert not Money(1, "IDR").is_zero()

    def test_is_positive(self) -> None:
        assert Money(1, "IDR").is_positive()
        assert not Money(0, "IDR").is_positive()
        assert not Money(-1, "IDR").is_positive()

    def test_is_negative(self) -> None:
        assert Money(-1, "IDR").is_negative()
        assert not Money(0, "IDR").is_negative()
        assert not Money(1, "IDR").is_negative()


# ── format ──────────────────────────────────────────────────


class TestFormat:
    def test_idr_no_decimals_dot_thousands(self) -> None:
        assert Money(15000, "IDR").format() == "Rp 15.000"
        assert Money(1500000, "IDR").format() == "Rp 1.500.000"
        assert Money(0, "IDR").format() == "Rp 0"

    def test_usd_two_decimals(self) -> None:
        assert Money(1500, "USD").format() == "$15.00"
        assert Money(0, "USD").format() == "$0.00"

    def test_eur_two_decimals(self) -> None:
        assert Money(1500, "EUR").format() == "€15.00"

    def test_rub_two_decimals(self) -> None:
        assert Money(1500, "RUB").format() == "15.00 ₽"

    def test_unknown_currency_falls_through(self) -> None:
        assert Money(1500, "JPY").format() == "15.00 JPY"

    def test_format_is_idempotent(self) -> None:
        # Round-trip is just for stability; we don't parse the string.
        m = Money(1234567, "IDR")
        assert m.format() == "Rp 1.234.567"
