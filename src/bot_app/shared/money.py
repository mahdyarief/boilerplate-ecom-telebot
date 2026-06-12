"""Money value object — integer smallest units per currency.

Single source of truth for monetary amounts. Every price in the system
flows through this type; float arithmetic is forbidden.

Note on IDR: Indonesian Rupiah has no sub-units in practice, so we treat
1 IDR as the smallest unit (``amount_minor == 1`` for Rp 1).  This keeps
the API uniform across currencies at the cost of an extra zero for
non-IDR stores (USD $15.00 → amount_minor=1500).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True, slots=True)
class Money:
    """Immutable money value: integer smallest-unit amount + ISO-4217 currency."""

    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int) or isinstance(self.amount_minor, bool):
            raise TypeError(f"amount_minor must be int, got {type(self.amount_minor).__name__}")
        if not isinstance(self.currency, str) or len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError(f"currency must be a 3-letter ISO code, got {self.currency!r}")
        # Normalize currency to upper-case for hashing/equality consistency
        object.__setattr__(self, "currency", self.currency.upper())

    # ── arithmetic ────────────────────────────────────────

    def __add__(self, other: Self) -> Self:
        self._assert_same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Self) -> Self:
        self._assert_same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __mul__(self, factor: int) -> Self:
        if not isinstance(factor, int) or isinstance(factor, bool):
            raise TypeError(f"factor must be int, got {type(factor).__name__}")
        return Money(self.amount_minor * factor, self.currency)

    __rmul__ = __mul__

    # ── comparison ────────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self.amount_minor == other.amount_minor and self.currency == other.currency

    def __lt__(self, other: Self) -> bool:
        self._assert_same_currency(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: Self) -> bool:
        self._assert_same_currency(other)
        return self.amount_minor <= other.amount_minor

    def __gt__(self, other: Self) -> bool:
        self._assert_same_currency(other)
        return self.amount_minor > other.amount_minor

    def __ge__(self, other: Self) -> bool:
        self._assert_same_currency(other)
        return self.amount_minor >= other.amount_minor

    def __hash__(self) -> int:
        return hash((self.amount_minor, self.currency))

    # ── helpers ───────────────────────────────────────────

    def is_zero(self) -> bool:
        return self.amount_minor == 0

    def is_positive(self) -> bool:
        return self.amount_minor > 0

    def is_negative(self) -> bool:
        return self.amount_minor < 0

    def format(self) -> str:
        """Human-readable string.  Crude but serviceable for v0."""
        c = self.currency
        a = self.amount_minor
        if c == "IDR":
            # Indonesian formatting: dots as thousands separator, no decimals
            return f"Rp {a:,.0f}".replace(",", ".")
        if c == "USD":
            return f"${a / 100:,.2f}"
        if c == "EUR":
            return f"€{a / 100:,.2f}"
        if c == "RUB":
            return f"{a / 100:,.2f} ₽"
        # Unknown currency — assume 2 decimal places
        return f"{a / 100:,.2f} {c}"

    @classmethod
    def zero(cls, currency: str) -> Self:
        return cls(0, currency)

    # ── private ───────────────────────────────────────────

    def _assert_same_currency(self, other: Self) -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"currency mismatch: {self.currency!r} vs {other.currency!r}"
            )

    def __repr__(self) -> str:  # pragma: no cover — debug aid
        return f"Money({self.amount_minor}, {self.currency!r})"
