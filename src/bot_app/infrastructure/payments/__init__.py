"""Payment provider stubs (Phase 0).

The real payment logic arrives in Phase 3.
This module only exposes type definitions so the rest of the codebase
can already reference the protocol.
"""

from __future__ import annotations

from typing import Protocol


class PaymentProvider(Protocol):
    """Interface that every payment provider must implement."""

    async def create_invoice_link(self, order_id: int, amount: int, currency: str) -> str: ...
    async def verify_payment(self, provider_charge_id: str) -> bool: ...
