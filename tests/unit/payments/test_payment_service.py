"""Tests for the unified PaymentService orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot_app.core.errors import PaymentError
from bot_app.infrastructure.payments.service import PaymentInvoice, PaymentService
from bot_app.infrastructure.payments.qris import validate_static_qris


# ── Helpers ────────────────────────────────────────────────

SAMPLE_STATIC_QRIS = (
    "00020101021126380014ID.CO.QRIS.WWW0116936000000000000"
    "05204581253033605802ID5908TestShop6007Jakarta6304F2F0"
)

# The QRIS above is this exact string (no line-break artifacts):
# 00020101021126380014ID.CO.QRIS.WWW011693600000000000005204581253033605802ID5908TestShop6007Jakarta6304F2F0


# ── ActiveProvider tests ──────────────────────────────────


class TestActiveProvider:
    def test_pakasir_takes_priority(self) -> None:
        svc = PaymentService()
        # Directly set _pakasir with a mock that has is_enabled=True
        mock_pakasir = MagicMock()
        mock_pakasir.is_enabled = True
        svc._pakasir = mock_pakasir

        with patch("bot_app.infrastructure.payments.service.settings") as mock_settings:
            mock_settings.QRIS_STATIC_PAYLOAD = "some_payload"
            mock_settings.PROVIDER_TOKEN = "some_token"
            assert svc.active_provider == "pakasir"

    def test_qris_when_no_pakasir(self) -> None:
        svc = PaymentService()
        mock_pakasir = MagicMock()
        mock_pakasir.is_enabled = False
        svc._pakasir = mock_pakasir

        with patch("bot_app.infrastructure.payments.service.settings") as mock_settings:
            mock_settings.QRIS_STATIC_PAYLOAD = "some_payload"
            mock_settings.PROVIDER_TOKEN = "some_token"
            assert svc.active_provider == "qris"

    def test_provider_token_when_no_qris(self) -> None:
        svc = PaymentService()
        mock_pakasir = MagicMock()
        mock_pakasir.is_enabled = False
        svc._pakasir = mock_pakasir

        with patch("bot_app.infrastructure.payments.service.settings") as mock_settings:
            mock_settings.QRIS_STATIC_PAYLOAD = ""
            mock_settings.PROVIDER_TOKEN = "some_token"
            assert svc.active_provider == "provider_token"

    def test_dev_mode_when_nothing_configured(self) -> None:
        svc = PaymentService()
        mock_pakasir = MagicMock()
        mock_pakasir.is_enabled = False
        svc._pakasir = mock_pakasir

        with patch("bot_app.infrastructure.payments.service.settings") as mock_settings:
            mock_settings.QRIS_STATIC_PAYLOAD = ""
            mock_settings.PROVIDER_TOKEN = ""
            assert svc.active_provider == "dev"


# ── GenerateUniqueCode tests ──────────────────────────────


class TestGenerateUniqueCode:
    def test_in_range(self) -> None:
        svc = PaymentService()
        for _ in range(100):
            code = svc.generate_unique_code()
            assert 100 <= code <= 999

    def test_generates_different_codes(self) -> None:
        svc = PaymentService()
        codes = {svc.generate_unique_code() for _ in range(50)}
        # Very unlikely to all be the same
        assert len(codes) > 1


# ── BuildQRISInvoice tests ────────────────────────────────


class TestBuildQRISInvoice:
    def test_successful_build(self) -> None:
        with patch("bot_app.infrastructure.payments.service.settings") as mock_settings:
            mock_settings.QRIS_STATIC_PAYLOAD = SAMPLE_STATIC_QRIS

            svc = PaymentService()
            invoice = svc.build_qris_invoice(
                order_id=1,
                base_amount=50000,
                unique_code=321,
            )

            assert isinstance(invoice, PaymentInvoice)
            assert invoice.order_id == 1
            assert invoice.amount == 50000
            assert invoice.unique_code == 321
            assert invoice.final_amount == 50321
            assert invoice.qris_payload is not None
            assert invoice.payment_url is None
            assert invoice.provider == "qris"
            assert invoice.payment_identifier.startswith("PAY-")

    def test_auto_unique_code(self) -> None:
        with patch("bot_app.infrastructure.payments.service.settings") as mock_settings:
            mock_settings.QRIS_STATIC_PAYLOAD = SAMPLE_STATIC_QRIS

            svc = PaymentService()
            invoice = svc.build_qris_invoice(order_id=1, base_amount=50000)

            assert 100 <= invoice.unique_code <= 999
            assert invoice.final_amount == 50000 + invoice.unique_code

    def test_zero_amount_rejected(self) -> None:
        with patch("bot_app.infrastructure.payments.service.settings") as mock_settings:
            mock_settings.QRIS_STATIC_PAYLOAD = SAMPLE_STATIC_QRIS

            svc = PaymentService()
            with pytest.raises(PaymentError, match="greater than 0"):
                svc.build_qris_invoice(order_id=1, base_amount=0)

    def test_no_static_payload_raises(self) -> None:
        with patch("bot_app.infrastructure.payments.service.settings") as mock_settings:
            mock_settings.QRIS_STATIC_PAYLOAD = ""

            svc = PaymentService()
            with pytest.raises(PaymentError, match="not configured"):
                svc.build_qris_invoice(order_id=1, base_amount=50000)

    def test_invalid_static_payload_raises(self) -> None:
        with patch("bot_app.infrastructure.payments.service.settings") as mock_settings:
            mock_settings.QRIS_STATIC_PAYLOAD = "invalid_qris_string"

            svc = PaymentService()
            with pytest.raises(PaymentError, match="Invalid QRIS"):
                svc.build_qris_invoice(order_id=1, base_amount=50000)

    def test_qris_payload_is_valid_dynamic(self) -> None:
        """The generated QRIS payload should be a valid dynamic QRIS."""
        with patch("bot_app.infrastructure.payments.service.settings") as mock_settings:
            mock_settings.QRIS_STATIC_PAYLOAD = SAMPLE_STATIC_QRIS

            svc = PaymentService()
            invoice = svc.build_qris_invoice(
                order_id=1, base_amount=50000, unique_code=321,
            )

            # Verify the output is valid dynamic QRIS
            result = validate_static_qris(invoice.qris_payload)
            assert result.valid is True

            # Should contain the final amount
            assert str(invoice.final_amount) in invoice.qris_payload


# ── CreatePakasirInvoice tests ────────────────────────────


class TestCreatePakasirInvoice:
    @pytest.mark.asyncio
    async def test_not_enabled_raises(self) -> None:
        svc = PaymentService()
        mock_pakasir = MagicMock()
        mock_pakasir.is_enabled = False
        mock_pakasir.close = AsyncMock()
        svc._pakasir = mock_pakasir

        with pytest.raises(PaymentError, match="not enabled"):
            await svc.create_pakasir_invoice(order_id=1, amount=50000)


# ── CreateInvoice orchestration tests ─────────────────────


class TestCreateInvoice:
    @pytest.mark.asyncio
    async def test_raises_when_only_dev_mode(self) -> None:
        """When no off-platform provider is configured, create_invoice should raise."""
        svc = PaymentService()
        mock_pakasir = MagicMock()
        mock_pakasir.is_enabled = False
        mock_pakasir.close = AsyncMock()
        svc._pakasir = mock_pakasir

        with patch("bot_app.infrastructure.payments.service.settings") as mock_settings:
            mock_settings.PAKASIR_ENABLED = False
            mock_settings.QRIS_STATIC_PAYLOAD = ""
            mock_settings.PROVIDER_TOKEN = ""

            with pytest.raises(PaymentError, match="No off-platform payment provider"):
                await svc.create_invoice(order_id=1, amount=50000)


# ── Close tests ──────────────────────────────────────────


class TestPaymentServiceClose:
    @pytest.mark.asyncio
    async def test_close_without_pakasir(self) -> None:
        """Closing a service without a Pakasir instance should not raise."""
        svc = PaymentService()
        svc._pakasir = None
        await svc.close()

    @pytest.mark.asyncio
    async def test_close_with_pakasir(self) -> None:
        svc = PaymentService()
        mock_pakasir = AsyncMock()
        svc._pakasir = mock_pakasir

        await svc.close()
        mock_pakasir.close.assert_called_once()
