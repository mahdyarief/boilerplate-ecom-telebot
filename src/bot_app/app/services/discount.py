"""Discount service — coupon redemption and validation logic.

All coupon operations run within a UnitOfWork transaction to ensure
atomic increment of used_count and prevent over-redemption.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from ...core.errors import CouponError
from ...infrastructure.persistence.uow import UnitOfWork

logger = logging.getLogger(__name__)


class DiscountService:
    """Orchestrates coupon redemption: validate → apply → increment used_count."""

    def __init__(self, session_factory) -> None:  # type: ignore[valid-type]
        self._session_factory = session_factory

    async def redeem_coupon(self, code: str) -> int:
        """Validate and redeem a coupon code.

        Returns the discount_percent if the coupon is valid.

        Raises
        ------
        CouponError
            If the coupon is invalid, expired, exhausted, or disabled.
        """
        async with UnitOfWork(self._session_factory) as uow:
            coupon = await uow.coupons.get_by_code(code.upper().strip())
            if coupon is None:
                raise CouponError("Kupon tidak ditemukan.")

            if not coupon.is_active:
                raise CouponError("Kupon sudah dinonaktifkan.")

            # Check expiry
            if coupon.expires_at is not None:
                now = datetime.now(UTC)
                exp = coupon.expires_at
                if exp.tzinfo is None:
                    from datetime import timezone
                    exp = exp.replace(tzinfo=timezone.utc)
                if now > exp:
                    raise CouponError("Kupon sudah kadaluarsa.")

            # Check usage limit
            if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
                raise CouponError("Kupon sudah habis digunakan.")

            # Validate discount range
            if not 0 < coupon.discount_percent <= 100:
                raise CouponError("Kupon tidak valid.")

            # Atomically increment usage
            await uow.coupons.increment_used(coupon.id)

            logger.info(
                "coupon redeemed: code=%s discount=%d%%",
                coupon.code,
                coupon.discount_percent,
            )

            return coupon.discount_percent

    async def validate_coupon(self, code: str) -> tuple[bool, str, int]:
        """Check if a coupon is valid without redeeming it.

        Returns ``(True, "", discount_percent)`` if valid, or
        ``(False, error_message, 0)`` if not.

        Unlike :meth:`redeem_coupon`, this method does **not** increment
        ``used_count``.  Use this when you only need to verify a coupon's
        validity (e.g. for UI feedback) without consuming it.
        """
        async with UnitOfWork(self._session_factory) as uow:
            coupon = await uow.coupons.get_by_code(code.upper().strip())
            if coupon is None:
                return False, "Kupon tidak ditemukan.", 0

            if not coupon.is_active:
                return False, "Kupon sudah dinonaktifkan.", 0

            # Check expiry
            if coupon.expires_at is not None:
                now = datetime.now(UTC)
                # Handle both offset-aware and offset-naive expires_at
                exp = coupon.expires_at
                if exp.tzinfo is None:
                    # Treat naive datetime as UTC
                    from datetime import timezone
                    exp = exp.replace(tzinfo=timezone.utc)
                if now > exp:
                    return False, "Kupon sudah kadaluarsa.", 0

            # Check usage limit
            if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
                return False, "Kupon sudah habis digunakan.", 0

            # Validate discount range
            if not 0 < coupon.discount_percent <= 100:
                return False, "Kupon tidak valid.", 0

            return True, "", coupon.discount_percent
