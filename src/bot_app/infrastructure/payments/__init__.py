"""Payment provider infrastructure — QRIS, Pakasir, and the provider registry.

Phase 3 payment infrastructure:

* :class:`PaymentProvider` — protocol that every payment provider must implement
* :mod:`.qris` — QRIS static-to-dynamic conversion provider
* :mod:`.pakasir` — Pakasir payment gateway HTTP client
* :mod:`.service` — unified ``PaymentService`` orchestrator
* :mod:`.registry` — lazy-initialised provider registry

Usage::

    from bot_app.infrastructure.payments import PaymentService

    svc = PaymentService()
    invoice = await svc.create_invoice(order_id=1, amount=50000)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .pakasir import (
    PakasirConfig,
    PakasirCreateResponse,
    PakasirPaymentData,
    PakasirService,
    PakasirTransactionData,
    PakasirTransactionDetailResponse,
    PakasirWebhookPayload,
)
from .qris import (
    TLV,
    QRISSummary,
    ValidationResult,
    build_tlv,
    convert_static_to_dynamic,
    crc16,
    parse_tlv,
    summarize_qris,
    validate_static_qris,
)
from .registry import get_provider, list_providers, register_provider
from .registry import reset as reset_registry
from .service import PaymentInvoice, PaymentService

# ── Protocol ────────────────────────────────────────────────


@runtime_checkable
class PaymentProvider(Protocol):
    """Interface that every payment provider must implement."""

    async def create_invoice_link(self, order_id: int, amount: int, currency: str) -> str: ...
    async def verify_payment(self, provider_charge_id: str) -> bool: ...
