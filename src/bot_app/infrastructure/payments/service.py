"""Unified payment service — orchestrates QRIS and Pakasir providers.

Provides a single ``PaymentService`` that:

* Picks the active payment provider (QRIS via Pakasir, or direct QRIS)
* Generates unique amount codes for QRIS reconciliation
* Creates invoices, checks payment status, and handles webhooks
* Falls back to Telegram's native payment when ``PROVIDER_TOKEN`` is set

This service is the main entry point for the checkout flow to create
payment requests without knowing the underlying provider implementation.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from ...core.config import settings
from ...core.errors import PaymentError
from .pakasir import PakasirConfig, PakasirService
from .qris import convert_static_to_dynamic, validate_static_qris

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PaymentInvoice:
    """A payment invoice returned by the service."""

    order_id: int
    amount: int
    unique_code: int
    final_amount: int
    qris_payload: str | None  # None when using Telegram Payments API
    payment_url: str | None  # Pakasir payment page URL (if applicable)
    provider: str  # "qris", "pakasir", or "provider_token"
    payment_identifier: str


class PaymentService:
    """Orchestrates payment creation across QRIS and Pakasir providers.

    Priority order:

    1. **Pakasir** (if ``PAKASIR_ENABLED`` is ``True`` and configured)
    2. **Direct QRIS** (if ``QRIS_STATIC_PAYLOAD`` is set)
    3. **Telegram Payments API** (if ``PROVIDER_TOKEN`` is set — handled
       by the checkout router sending a Telegram invoice)

    When none of the above are configured, the checkout flow falls back
    to dev-mode auto-confirmation.
    """

    def __init__(self) -> None:
        self._pakasir: PakasirService | None = None

    @property
    def pakasir(self) -> PakasirService:
        """Lazy-initialised Pakasir service."""
        if self._pakasir is None:
            self._pakasir = PakasirService(PakasirConfig.from_settings())
        return self._pakasir

    @property
    def active_provider(self) -> str:
        """Return the name of the currently active payment provider."""
        if self.pakasir.is_enabled:
            return "pakasir"
        if settings.QRIS_STATIC_PAYLOAD.strip():
            return "qris"
        if settings.PROVIDER_TOKEN.strip():
            return "provider_token"
        return "dev"

    def generate_unique_code(self) -> int:
        """Generate a unique suffix (100–999) to append to the base amount.

        This allows payment reconciliation by matching the exact paid amount
        (base + unique_code) against outstanding invoices.
        """
        return 100 + secrets.randbelow(900)  # 100..999

    def build_qris_invoice(
        self,
        order_id: int,
        base_amount: int,
        *,
        unique_code: int | None = None,
        static_qris: str | None = None,
    ) -> PaymentInvoice:
        """Build a QRIS payment invoice from the static QRIS payload.

        Parameters
        ----------
        order_id : int
            The order ID for tracking.
        base_amount : int
            The order total in smallest currency unit.
        unique_code : int | None
            A unique code to append to the amount (auto-generated if None).
        static_qris : str | None
            Override the static QRIS payload (defaults to settings).

        Returns
        -------
        PaymentInvoice
        """
        if base_amount <= 0:
            raise PaymentError("Amount must be greater than 0")

        payload = static_qris or settings.QRIS_STATIC_PAYLOAD.strip()
        if not payload:
            raise PaymentError("QRIS static payload not configured")

        validation = validate_static_qris(payload)
        if not validation.valid:
            raise PaymentError(
                "Invalid QRIS payload: " + "; ".join(validation.errors)
            )

        if unique_code is None:
            unique_code = self.generate_unique_code()

        final_amount = base_amount + unique_code
        qris_payload = convert_static_to_dynamic(payload, final_amount)
        payment_identifier = f"PAY-{secrets.token_hex(4).upper()}"

        return PaymentInvoice(
            order_id=order_id,
            amount=base_amount,
            unique_code=unique_code,
            final_amount=final_amount,
            qris_payload=qris_payload,
            payment_url=None,
            provider="qris",
            payment_identifier=payment_identifier,
        )

    async def create_pakasir_invoice(
        self,
        order_id: int,
        amount: int,
    ) -> PaymentInvoice:
        """Create a payment invoice via the Pakasir gateway.

        Parameters
        ----------
        order_id : int
            The order ID for tracking.
        amount : int
            The order total in smallest currency unit.

        Returns
        -------
        PaymentInvoice
        """
        if not self.pakasir.is_enabled:
            raise PaymentError("Pakasir provider is not enabled")

        payment_identifier = f"PAY-{secrets.token_hex(4).upper()}"
        resp = await self.pakasir.create_transaction(
            order_id=payment_identifier,
            amount=amount,
            method="qris",
        )

        payment_url = self.pakasir.generate_payment_url(
            payment_identifier, amount
        )

        return PaymentInvoice(
            order_id=order_id,
            amount=amount,
            unique_code=0,
            final_amount=resp.payment.total_payment,
            qris_payload=resp.payment.payment_number or None,
            payment_url=payment_url,
            provider="pakasir",
            payment_identifier=payment_identifier,
        )

    async def create_invoice(
        self,
        order_id: int,
        amount: int,
    ) -> PaymentInvoice:
        """Create a payment invoice using the best available provider.

        Falls through providers in priority order.

        Parameters
        ----------
        order_id : int
            The order ID.
        amount : int
            Order total in smallest currency unit.

        Returns
        -------
        PaymentInvoice
        """
        provider = self.active_provider

        if provider == "pakasir":
            return await self.create_pakasir_invoice(order_id, amount)

        if provider == "qris":
            return self.build_qris_invoice(order_id, amount)

        # provider_token and dev modes are handled by the checkout router
        # (Telegram native Payments API or dev auto-confirm)
        raise PaymentError(
            f"No off-platform payment provider configured. "
            f"Active provider: {provider}"
        )

    async def close(self) -> None:
        """Clean up resources (close HTTP sessions)."""
        if self._pakasir is not None:
            await self._pakasir.close()
