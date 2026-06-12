"""Pakasir payment provider — HTTP client for the Pakasir payment gateway.

Ported from the Go reference implementation at ``kvc-gate/internal/payments/pakasir.go``.
Pakasir is an Indonesian payment gateway that supports QRIS, virtual accounts,
and other payment methods via a simple REST API.

This module provides:

* :class:`PakasirConfig` — provider configuration
* :class:`PakasirService` — async HTTP client for create/detail/cancel transactions
* :class:`PakasirWebhookPayload` — webhook payload model
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import aiohttp

from ...core.config import settings

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────

DEFAULT_PAKASIR_BASE_URL = "https://app.pakasir.com"


# ── Data classes ─────────────────────────────────────────────


@dataclass(slots=True)
class PakasirConfig:
    """Pakasir provider configuration (loaded from Settings)."""

    project_slug: str
    api_key: str
    enabled: bool
    base_url: str = DEFAULT_PAKASIR_BASE_URL

    @classmethod
    def from_settings(cls) -> PakasirConfig:
        """Load Pakasir config from the application settings."""
        return cls(
            project_slug=settings.PAKASIR_PROJECT_SLUG.strip(),
            api_key=settings.PAKASIR_API_KEY.strip(),
            enabled=settings.PAKASIR_ENABLED,
            base_url=settings.PAKASIR_BASE_URL.strip() or DEFAULT_PAKASIR_BASE_URL,
        )

    @property
    def is_configured(self) -> bool:
        """True when project_slug and api_key are both non-empty."""
        return bool(self.project_slug and self.api_key)


@dataclass(slots=True)
class PakasirPaymentData:
    """Payment data returned from a successful create-transaction call."""

    project: str
    order_id: str
    amount: int
    fee: int
    total_payment: int
    payment_method: str
    payment_number: str
    expired_at: str


@dataclass(slots=True)
class PakasirCreateResponse:
    """Response from creating a Pakasir transaction."""

    payment: PakasirPaymentData


@dataclass(slots=True)
class PakasirTransactionData:
    """Transaction detail from a get-transaction-detail call."""

    amount: int
    order_id: str
    project: str
    status: str
    payment_method: str
    completed_at: str


@dataclass(slots=True)
class PakasirTransactionDetailResponse:
    """Response from a transaction detail query."""

    transaction: PakasirTransactionData


@dataclass(slots=True)
class PakasirWebhookPayload:
    """Payload received from Pakasir webhook callback."""

    amount: int
    order_id: str
    project: str
    status: str
    payment_method: str
    completed_at: str


# ── Service ──────────────────────────────────────────────────


class PakasirService:
    """Async HTTP client for the Pakasir payment gateway.

    All methods are async and use ``aiohttp`` for HTTP requests.
    The service reads its configuration from :class:`PakasirConfig.from_settings`.
    """

    def __init__(self, config: PakasirConfig | None = None) -> None:
        self._config = config or PakasirConfig.from_settings()
        self._session: aiohttp.ClientSession | None = None

    @property
    def config(self) -> PakasirConfig:
        return self._config

    @property
    def is_enabled(self) -> bool:
        """Check if the provider is enabled and properly configured."""
        return self._config.enabled and self._config.is_configured

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session (lazy initialization)."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def create_transaction(
        self,
        *,
        order_id: str,
        amount: int,
        method: str = "qris",
    ) -> PakasirCreateResponse:
        """Create a new payment transaction via the Pakasir API.

        Parameters
        ----------
        order_id : str
            Unique order identifier (e.g. ``PAY-REQ-1``).
        amount : int
            Payment amount in smallest currency unit.
        method : str
            Payment method (default ``"qris"``).

        Returns
        -------
        PakasirCreateResponse

        Raises
        ------
        PaymentError
            If the request fails or the response is invalid.
        """
        from ...core.errors import PaymentError

        if not self.is_enabled:
            raise PaymentError("Pakasir provider is not enabled or not configured.")

        method = method.strip() or "qris"
        req_body: dict[str, Any] = {
            "project": self._config.project_slug,
            "order_id": order_id,
            "amount": amount,
            "api_key": self._config.api_key,
        }

        api_url = f"{self._config.base_url}/api/transactioncreate/{method}"
        session = await self._get_session()

        try:
            async with session.post(api_url, json=req_body) as resp:
                body = await resp.text()

                if resp.status >= 400:
                    try:
                        err_data = json.loads(body)
                        err_msg = err_data.get("message", body)
                    except (json.JSONDecodeError, AttributeError):
                        err_msg = body
                    raise PaymentError(
                        f"Pakasir server error (HTTP {resp.status}): {err_msg}"
                    )

                data = json.loads(body)
                payment_data = data.get("payment", {})
                if not payment_data.get("order_id"):
                    raise PaymentError(
                        "Pakasir transaction failed: empty order_id in response"
                    )

                return PakasirCreateResponse(
                    payment=PakasirPaymentData(
                        project=payment_data.get("project", ""),
                        order_id=payment_data["order_id"],
                        amount=payment_data.get("amount", 0),
                        fee=payment_data.get("fee", 0),
                        total_payment=payment_data.get("total_payment", 0),
                        payment_method=payment_data.get("payment_method", ""),
                        payment_number=payment_data.get("payment_number", ""),
                        expired_at=payment_data.get("expired_at", ""),
                    )
                )
        except PaymentError:
            raise
        except aiohttp.ClientError as exc:
            raise PaymentError(
                f"Pakasir connection failed: unable to reach {api_url}: {exc}"
            ) from exc
        except Exception as exc:
            raise PaymentError(f"Pakasir unexpected error: {exc}") from exc

    async def get_transaction_detail(
        self,
        order_id: str,
        amount: int,
    ) -> PakasirTransactionDetailResponse:
        """Get the status of an existing transaction.

        Parameters
        ----------
        order_id : str
            The order identifier used when creating the transaction.
        amount : int
            The transaction amount.

        Returns
        -------
        PakasirTransactionDetailResponse
        """
        from ...core.errors import PaymentError

        if not self.is_enabled:
            raise PaymentError("Pakasir provider is not enabled or not configured.")

        api_url = f"{self._config.base_url}/api/transactiondetail"
        params = {
            "project": self._config.project_slug,
            "order_id": order_id,
            "amount": str(amount),
            "api_key": self._config.api_key,
        }
        session = await self._get_session()

        try:
            async with session.get(api_url, params=params) as resp:
                body = await resp.text()

                if resp.status != 200:
                    raise PaymentError(
                        f"Pakasir page error (HTTP {resp.status})"
                    )

                data = json.loads(body)
                txn_data = data.get("transaction", {})

                return PakasirTransactionDetailResponse(
                    transaction=PakasirTransactionData(
                        amount=txn_data.get("amount", 0),
                        order_id=txn_data.get("order_id", ""),
                        project=txn_data.get("project", ""),
                        status=txn_data.get("status", ""),
                        payment_method=txn_data.get("payment_method", ""),
                        completed_at=txn_data.get("completed_at", ""),
                    )
                )
        except PaymentError:
            raise
        except aiohttp.ClientError as exc:
            raise PaymentError(
                f"Pakasir request failed: {exc}"
            ) from exc
        except Exception as exc:
            raise PaymentError(f"Pakasir unexpected error: {exc}") from exc

    async def cancel_transaction(
        self,
        *,
        order_id: str,
        amount: int,
    ) -> None:
        """Cancel an existing transaction.

        Parameters
        ----------
        order_id : str
            The order identifier used when creating the transaction.
        amount : int
            The transaction amount.

        Raises
        ------
        PaymentError
            If the cancellation request fails.
        """
        from ...core.errors import PaymentError

        if not self.is_enabled:
            raise PaymentError("Pakasir provider is not enabled or not configured.")

        req_body: dict[str, Any] = {
            "project": self._config.project_slug,
            "order_id": order_id,
            "amount": amount,
            "api_key": self._config.api_key,
        }

        api_url = f"{self._config.base_url}/api/transactioncancel"
        session = await self._get_session()

        try:
            async with session.post(api_url, json=req_body) as resp:
                body = await resp.text()

                if resp.status >= 400:
                    try:
                        err_data = json.loads(body)
                        err_msg = err_data.get("message", body)
                    except (json.JSONDecodeError, AttributeError):
                        err_msg = body
                    raise PaymentError(
                        f"Pakasir server error (HTTP {resp.status}): {err_msg}"
                    )
        except PaymentError:
            raise
        except aiohttp.ClientError as exc:
            raise PaymentError(
                f"Pakasir connection failed: unable to reach {api_url}: {exc}"
            ) from exc
        except Exception as exc:
            raise PaymentError(f"Pakasir unexpected error: {exc}") from exc

    # ── URL helpers ────────────────────────────────────────

    def generate_payment_url(self, order_id: str, amount: int) -> str:
        """Generate the Pakasir payment page URL for a transaction."""
        from urllib.parse import quote

        base = f"{self._config.base_url}/pay/{self._config.project_slug}/{amount}"
        return f"{base}?order_id={quote(order_id)}"

    def generate_payment_url_with_redirect(
        self, order_id: str, amount: int, redirect_url: str
    ) -> str:
        """Generate the Pakasir payment page URL with a redirect after payment."""
        from urllib.parse import quote

        base = self.generate_payment_url(order_id, amount)
        if redirect_url:
            base += f"&redirect={quote(redirect_url)}"
        return base
