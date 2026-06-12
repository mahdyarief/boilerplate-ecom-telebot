"""Tests for the Pakasir payment provider module.

Ported test cases from the Go reference implementation at
``kvc-gate/internal/payments/pakasir_test.go`` plus additional Python-specific tests.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot_app.core.errors import PaymentError
from bot_app.infrastructure.payments.pakasir import (
    DEFAULT_PAKASIR_BASE_URL,
    PakasirConfig,
    PakasirCreateResponse,
    PakasirPaymentData,
    PakasirService,
    PakasirTransactionData,
    PakasirTransactionDetailResponse,
    PakasirWebhookPayload,
)


# ── Fixtures ────────────────────────────────────────────────


def _make_config(**overrides) -> PakasirConfig:
    defaults = {
        "project_slug": "test-project",
        "api_key": "test-api-key",
        "enabled": True,
        "base_url": DEFAULT_PAKASIR_BASE_URL,
    }
    defaults.update(overrides)
    return PakasirConfig(**defaults)


@pytest.fixture
def config() -> PakasirConfig:
    return _make_config()


@pytest.fixture
def service(config: PakasirConfig) -> PakasirService:
    return PakasirService(config)


class _MockResponse:
    """A mock aiohttp response that supports async context manager."""

    def __init__(self, status: int, text: str) -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _MockSession:
    """A mock aiohttp.ClientSession that supports async context manager on post/get."""

    def __init__(self) -> None:
        self.responses: list[_MockResponse] = []
        self._call_index = 0
        self.last_post_url: str = ""
        self.last_post_json: dict = {}
        self.last_get_url: str = ""
        self.last_get_params: dict = {}

    def add_response(self, status: int, text: str) -> None:
        self.responses.append(_MockResponse(status, text))

    def post(self, url: str, **kwargs) -> _MockResponse:
        self.last_post_url = url
        self.last_post_json = kwargs.get("json", {})
        resp = self.responses[self._call_index]
        self._call_index += 1
        return resp

    def get(self, url: str, **kwargs) -> _MockResponse:
        self.last_get_url = url
        self.last_get_params = kwargs.get("params", {})
        resp = self.responses[self._call_index]
        self._call_index += 1
        return resp

    @property
    def closed(self) -> bool:
        return False

    async def close(self) -> None:
        pass


# ── PakasirConfig tests ────────────────────────────────────


class TestPakasirConfig:
    def test_is_configured_with_credentials(self) -> None:
        cfg = _make_config(project_slug="my-project", api_key="my-key")
        assert cfg.is_configured is True

    def test_not_configured_without_slug(self) -> None:
        cfg = _make_config(project_slug="", api_key="my-key")
        assert cfg.is_configured is False

    def test_not_configured_without_api_key(self) -> None:
        cfg = _make_config(project_slug="my-project", api_key="")
        assert cfg.is_configured is False

    def test_default_base_url(self) -> None:
        cfg = _make_config()
        assert cfg.base_url == DEFAULT_PAKASIR_BASE_URL


class TestPakasirConfigFromSettings:
    def test_loads_from_settings(self) -> None:
        from bot_app.core.config import Settings

        s = Settings(
            PAKASIR_PROJECT_SLUG="depodomain",
            PAKASIR_API_KEY="xxx123",
            PAKASIR_ENABLED=True,
            BOT_TOKEN="t",
        )
        with patch("bot_app.infrastructure.payments.pakasir.settings", s):
            cfg = PakasirConfig.from_settings()
            assert cfg.project_slug == "depodomain"
            assert cfg.api_key == "xxx123"
            assert cfg.enabled is True


# ── IsEnabled tests ────────────────────────────────────────


class TestPakasirIsEnabled:
    def test_enabled_and_configured(self, service: PakasirService) -> None:
        assert service.is_enabled is True

    def test_disabled_even_if_configured(self) -> None:
        cfg = _make_config(enabled=False)
        svc = PakasirService(cfg)
        assert svc.is_enabled is False

    def test_enabled_but_not_configured(self) -> None:
        cfg = _make_config(project_slug="", api_key="")
        svc = PakasirService(cfg)
        assert svc.is_enabled is False


# ── GeneratePaymentURL tests ───────────────────────────────


class TestGeneratePaymentURL:
    def test_basic_url(self, service: PakasirService) -> None:
        url = service.generate_payment_url("PAY-ABC", 22000)
        expected = f"{DEFAULT_PAKASIR_BASE_URL}/pay/test-project/22000?order_id=PAY-ABC"
        assert url == expected

    def test_url_with_redirect(self, service: PakasirService) -> None:
        url = service.generate_payment_url_with_redirect(
            "PAY-ABC", 22000, "https://example.com/callback"
        )
        assert "order_id=PAY-ABC" in url
        assert "redirect=" in url
        assert "example.com" in url

    def test_url_without_redirect(self, service: PakasirService) -> None:
        url = service.generate_payment_url_with_redirect("PAY-ABC", 22000, "")
        assert "redirect=" not in url


# ── CreateTransaction tests ────────────────────────────────


class TestPakasirCreateTransaction:
    @pytest.mark.asyncio
    async def test_not_enabled_raises(self) -> None:
        cfg = _make_config(enabled=False)
        svc = PakasirService(cfg)
        with pytest.raises(PaymentError, match="not enabled"):
            await svc.create_transaction(order_id="PAY-1", amount=99000)

    @pytest.mark.asyncio
    async def test_successful_create(self, service: PakasirService) -> None:
        """Test a successful transaction creation with a mocked HTTP response."""
        mock_session = _MockSession()
        mock_session.add_response(200, json.dumps({
            "payment": {
                "project": "test-project",
                "order_id": "PAY-ABC",
                "amount": 99000,
                "fee": 1003,
                "total_payment": 100003,
                "payment_method": "qris",
                "payment_number": "000201010212",
                "expired_at": "2025-09-19T01:18:49Z",
            }
        }))
        service._session = mock_session

        result = await service.create_transaction(order_id="PAY-ABC", amount=99000)

        assert isinstance(result, PakasirCreateResponse)
        assert result.payment.order_id == "PAY-ABC"
        assert result.payment.total_payment == 100003
        assert result.payment.payment_method == "qris"

    @pytest.mark.asyncio
    async def test_server_error_raises(self, service: PakasirService) -> None:
        """Test that a 4xx/5xx response raises PaymentError."""
        mock_session = _MockSession()
        mock_session.add_response(400, json.dumps({
            "message": "Invalid request"
        }))
        service._session = mock_session

        with pytest.raises(PaymentError, match="HTTP 400"):
            await service.create_transaction(order_id="PAY-ABC", amount=99000)

    @pytest.mark.asyncio
    async def test_empty_order_id_in_response_raises(self, service: PakasirService) -> None:
        """Test that an empty order_id in the response raises PaymentError."""
        mock_session = _MockSession()
        mock_session.add_response(200, json.dumps({
            "payment": {
                "project": "test-project",
                "order_id": "",
                "amount": 99000,
            }
        }))
        service._session = mock_session

        with pytest.raises(PaymentError, match="empty order_id"):
            await service.create_transaction(order_id="PAY-ABC", amount=99000)

    @pytest.mark.asyncio
    async def test_default_method_is_qris(self, service: PakasirService) -> None:
        """Default payment method should be 'qris'."""
        mock_session = _MockSession()
        mock_session.add_response(200, json.dumps({
            "payment": {
                "project": "test-project",
                "order_id": "PAY-1",
                "amount": 50000,
                "fee": 500,
                "total_payment": 50500,
                "payment_method": "qris",
                "payment_number": "qr123",
                "expired_at": "2025-01-01T00:00:00Z",
            }
        }))
        service._session = mock_session

        result = await service.create_transaction(order_id="PAY-1", amount=50000)
        assert result.payment.payment_method == "qris"

        # Verify the URL used 'qris'
        assert "/api/transactioncreate/qris" in mock_session.last_post_url

    @pytest.mark.asyncio
    async def test_request_body_contains_config_values(self, service: PakasirService) -> None:
        """Verify the request body sent to the API."""
        mock_session = _MockSession()
        mock_session.add_response(200, json.dumps({
            "payment": {
                "project": "test-project",
                "order_id": "PAY-1",
                "amount": 50000,
                "fee": 500,
                "total_payment": 50500,
                "payment_method": "qris",
                "payment_number": "qr123",
                "expired_at": "2025-01-01T00:00:00Z",
            }
        }))
        service._session = mock_session

        await service.create_transaction(order_id="PAY-1", amount=50000)

        assert mock_session.last_post_json["project"] == "test-project"
        assert mock_session.last_post_json["api_key"] == "test-api-key"
        assert mock_session.last_post_json["order_id"] == "PAY-1"
        assert mock_session.last_post_json["amount"] == 50000


# ── GetTransactionDetail tests ─────────────────────────────


class TestPakasirGetTransactionDetail:
    @pytest.mark.asyncio
    async def test_not_enabled_raises(self) -> None:
        cfg = _make_config(enabled=False)
        svc = PakasirService(cfg)
        with pytest.raises(PaymentError, match="not enabled"):
            await svc.get_transaction_detail("PAY-1", 50000)

    @pytest.mark.asyncio
    async def test_successful_detail(self, service: PakasirService) -> None:
        mock_session = _MockSession()
        mock_session.add_response(200, json.dumps({
            "transaction": {
                "amount": 22000,
                "order_id": "PAY-ABC",
                "project": "test-project",
                "status": "completed",
                "payment_method": "qris",
                "completed_at": "2024-09-10T08:07:02Z",
            }
        }))
        service._session = mock_session

        result = await service.get_transaction_detail("PAY-ABC", 22000)
        assert result.transaction.status == "completed"
        assert result.transaction.order_id == "PAY-ABC"

    @pytest.mark.asyncio
    async def test_non_200_raises(self, service: PakasirService) -> None:
        mock_session = _MockSession()
        mock_session.add_response(500, "Internal Server Error")
        service._session = mock_session

        with pytest.raises(PaymentError, match="HTTP 500"):
            await service.get_transaction_detail("PAY-ABC", 22000)


# ── CancelTransaction tests ────────────────────────────────


class TestPakasirCancelTransaction:
    @pytest.mark.asyncio
    async def test_not_enabled_raises(self) -> None:
        cfg = _make_config(enabled=False)
        svc = PakasirService(cfg)
        with pytest.raises(PaymentError, match="not enabled"):
            await svc.cancel_transaction(order_id="PAY-1", amount=99000)

    @pytest.mark.asyncio
    async def test_successful_cancel(self, service: PakasirService) -> None:
        mock_session = _MockSession()
        mock_session.add_response(200, "ok")
        service._session = mock_session

        # Should not raise
        await service.cancel_transaction(order_id="PAY-ABC", amount=99000)

    @pytest.mark.asyncio
    async def test_server_error_on_cancel(self, service: PakasirService) -> None:
        mock_session = _MockSession()
        mock_session.add_response(400, json.dumps({
            "message": "Not found"
        }))
        service._session = mock_session

        with pytest.raises(PaymentError, match="HTTP 400"):
            await service.cancel_transaction(order_id="PAY-ABC", amount=99000)


# ── Session management ─────────────────────────────────────


class TestPakasirSessionManagement:
    @pytest.mark.asyncio
    async def test_close_session(self, service: PakasirService) -> None:
        """Closing a service with no session should not raise."""
        await service.close()

    @pytest.mark.asyncio
    async def test_close_active_session(self, service: PakasirService) -> None:
        mock_session = AsyncMock()
        mock_session.closed = False
        service._session = mock_session

        await service.close()
        mock_session.close.assert_called_once()
