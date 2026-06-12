"""Tests for Phase 5 config validators and derived properties."""

from __future__ import annotations

import os
import pytest

from bot_app.core.config import Settings


class TestConfigValidators:
    def test_currency_3_letter_valid(self) -> None:
        s = Settings(CURRENCY="usd", BOT_TOKEN="t")
        assert s.CURRENCY == "USD"  # uppercased by validator

    def test_currency_invalid_2_letters(self) -> None:
        with pytest.raises(ValueError, match="3-letter"):
            Settings(CURRENCY="US", BOT_TOKEN="t")

    def test_currency_invalid_4_letters(self) -> None:
        with pytest.raises(ValueError, match="3-letter"):
            Settings(CURRENCY="DOLL", BOT_TOKEN="t")

    def test_currency_invalid_non_alpha(self) -> None:
        with pytest.raises(ValueError, match="3-letter"):
            Settings(CURRENCY="123", BOT_TOKEN="t")

    def test_log_level_valid(self) -> None:
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            s = Settings(LOG_LEVEL=level, BOT_TOKEN="t")
            assert s.LOG_LEVEL == level

    def test_log_level_lower_case(self) -> None:
        s = Settings(LOG_LEVEL="debug", BOT_TOKEN="t")
        assert s.LOG_LEVEL == "DEBUG"

    def test_log_level_invalid(self) -> None:
        with pytest.raises(ValueError, match="LOG_LEVEL"):
            Settings(LOG_LEVEL="VERBOSE", BOT_TOKEN="t")

    def test_rate_limit_rps_positive(self) -> None:
        s = Settings(RATE_LIMIT_PER_SECOND=2.5, BOT_TOKEN="t")
        assert s.RATE_LIMIT_PER_SECOND == 2.5

    def test_rate_limit_rps_zero(self) -> None:
        with pytest.raises(ValueError, match="RATE_LIMIT_PER_SECOND"):
            Settings(RATE_LIMIT_PER_SECOND=0, BOT_TOKEN="t")

    def test_rate_limit_rps_negative(self) -> None:
        with pytest.raises(ValueError, match="RATE_LIMIT_PER_SECOND"):
            Settings(RATE_LIMIT_PER_SECOND=-1, BOT_TOKEN="t")

    def test_rate_limit_burst_positive(self) -> None:
        s = Settings(RATE_LIMIT_BURST=10, BOT_TOKEN="t")
        assert s.RATE_LIMIT_BURST == 10

    def test_rate_limit_burst_zero(self) -> None:
        with pytest.raises(ValueError, match="RATE_LIMIT_BURST"):
            Settings(RATE_LIMIT_BURST=0, BOT_TOKEN="t")

    def test_graceful_shutdown_timeout_positive(self) -> None:
        s = Settings(GRACEFUL_SHUTDOWN_TIMEOUT=30, BOT_TOKEN="t")
        assert s.GRACEFUL_SHUTDOWN_TIMEOUT == 30

    def test_graceful_shutdown_timeout_zero(self) -> None:
        with pytest.raises(ValueError, match="GRACEFUL_SHUTDOWN_TIMEOUT"):
            Settings(GRACEFUL_SHUTDOWN_TIMEOUT=0, BOT_TOKEN="t")


class TestQRISConfigValidators:
    def test_qris_invoice_expiry_positive(self) -> None:
        s = Settings(QRIS_INVOICE_EXPIRY_MINUTES=30, BOT_TOKEN="t")
        assert s.QRIS_INVOICE_EXPIRY_MINUTES == 30

    def test_qris_invoice_expiry_zero(self) -> None:
        with pytest.raises(ValueError, match="QRIS_INVOICE_EXPIRY_MINUTES"):
            Settings(QRIS_INVOICE_EXPIRY_MINUTES=0, BOT_TOKEN="t")

    def test_qris_invoice_expiry_negative(self) -> None:
        with pytest.raises(ValueError, match="QRIS_INVOICE_EXPIRY_MINUTES"):
            Settings(QRIS_INVOICE_EXPIRY_MINUTES=-5, BOT_TOKEN="t")


class TestConfigDerivedProperties:
    def test_admin_ids_empty(self) -> None:
        s = Settings(ADMINS="", BOT_TOKEN="t")
        assert s.admin_ids == []

    def test_admin_ids_single(self) -> None:
        s = Settings(ADMINS="123", BOT_TOKEN="t")
        assert s.admin_ids == [123]

    def test_admin_ids_multiple(self) -> None:
        s = Settings(ADMINS="123,456,789", BOT_TOKEN="t")
        assert s.admin_ids == [123, 456, 789]

    def test_admin_ids_trailing_comma(self) -> None:
        s = Settings(ADMINS="123,", BOT_TOKEN="t")
        assert s.admin_ids == [123]

    def test_allowed_updates_list(self) -> None:
        s = Settings(ALLOWED_UPDATES="message,callback_query", BOT_TOKEN="t")
        assert s.allowed_updates_list == ["message", "callback_query"]

    def test_allowed_updates_empty(self) -> None:
        s = Settings(ALLOWED_UPDATES="", BOT_TOKEN="t")
        assert s.allowed_updates_list == []

    def test_is_production_webhook(self) -> None:
        s = Settings(USE_WEBHOOK=True, DATABASE_URL="sqlite+aiosqlite:///test.db", BOT_TOKEN="t")
        assert s.is_production is True

    def test_is_production_postgres(self) -> None:
        s = Settings(
            USE_WEBHOOK=False,
            DATABASE_URL="postgresql+psycopg://bot:bot@localhost/bot",
            BOT_TOKEN="t",
        )
        assert s.is_production is True

    def test_is_not_production(self) -> None:
        s = Settings(
            USE_WEBHOOK=False,
            DATABASE_URL="sqlite+aiosqlite:///test.db",
            BOT_TOKEN="t",
        )
        assert s.is_production is False

    def test_safe_database_url_sqlite(self) -> None:
        s = Settings(DATABASE_URL="sqlite+aiosqlite:///data/bot.db", BOT_TOKEN="t")
        assert s.safe_database_url == "sqlite+aiosqlite:///data/bot.db"

    def test_safe_database_url_postgres(self) -> None:
        s = Settings(
            DATABASE_URL="postgresql+psycopg://bot:secret@postgres:5432/bot",
            BOT_TOKEN="t",
        )
        assert s.safe_database_url == "postgresql+psycopg://bot:***@postgres:5432/bot"
        assert "secret" not in s.safe_database_url

    def test_safe_database_url_postgres_no_password(self) -> None:
        s = Settings(
            DATABASE_URL="postgresql+psycopg://bot@localhost/bot",
            BOT_TOKEN="t",
        )
        assert "bot@localhost" in s.safe_database_url

    def test_defaults(self) -> None:
        s = Settings(BOT_TOKEN="t")
        assert s.RATE_LIMIT_PER_SECOND == 1.0
        assert s.RATE_LIMIT_BURST == 5
        assert s.GRACEFUL_SHUTDOWN_TIMEOUT == 10
        assert s.SENTRY_DSN == ""
        assert s.ALLOWED_UPDATES == "message,callback_query,pre_checkout_query"
        assert s.PAKASIR_PROJECT_SLUG == ""
        assert s.PAKASIR_API_KEY == ""
        assert s.PAKASIR_ENABLED is False
        assert s.PAKASIR_BASE_URL == "https://app.pakasir.com"
        assert s.QRIS_STATIC_PAYLOAD == ""
        assert s.QRIS_INVOICE_EXPIRY_MINUTES == 15
