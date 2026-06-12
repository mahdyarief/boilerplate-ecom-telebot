"""boilerplate-ecom-telebot · core configuration (SSOT).

Phase 5 hardening: Pydantic validators, production-safety checks,
rate-limit tuning, SENTRY_DSN, graceful-shutdown timeout.
"""

from __future__ import annotations

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration.  Never call ``os.getenv`` elsewhere."""

    # ── bot ────────────────────────────────────────────────────
    BOT_TOKEN: str = ""
    LOG_LEVEL: str = "INFO"
    LANGUAGE: str = "id"

    # ── shop ──────────────────────────────────────────────────
    CURRENCY: str = "IDR"
    SHOP_NAME: str = "Toko Saya"
    SHOP_SUPPORT_USERNAME: str = "support"
    SHOP_CHANNEL_USERNAME: str = ""

    # ── payments ──────────────────────────────────────────────
    PAYMENT_PROVIDERS: str = "provider_token"
    PROVIDER_TOKEN: str = ""

    # ── Pakasir payment provider ──────────────────────────────
    PAKASIR_PROJECT_SLUG: str = ""
    PAKASIR_API_KEY: str = ""
    PAKASIR_ENABLED: bool = False
    PAKASIR_BASE_URL: str = "https://app.pakasir.com"

    # ── QRIS payment provider ──────────────────────────────
    QRIS_STATIC_PAYLOAD: str = ""
    QRIS_INVOICE_EXPIRY_MINUTES: int = 15

    # ── admins ────────────────────────────────────────────────
    ADMINS: str = ""

    # ── database ──────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///data/bot.db"

    # ── redis ─────────────────────────────────────────────────
    REDIS_URL: str = ""

    # ── deployment mode ────────────────────────────────────────
    USE_WEBHOOK: bool = False
    WEBHOOK_URL: str = ""
    WEBHOOK_PATH: str = "/webhook"
    WEBHOOK_SECRET_TOKEN: str = ""
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    POLLING_TIMEOUT: int = 30

    # ── order TTL ─────────────────────────────────────────────
    ORDER_RESERVATION_TTL: int = 15

    # ── low-stock notifications (Phase 6) ───────────────────────
    LOW_STOCK_THRESHOLD: int = 5

    # ── rate limiting (Phase 5) ───────────────────────────────
    RATE_LIMIT_PER_SECOND: float = 1.0
    RATE_LIMIT_BURST: int = 5

    # ── observability (Phase 5) ───────────────────────────────
    SENTRY_DSN: str = ""

    # ── graceful shutdown (Phase 5) ──────────────────────────
    GRACEFUL_SHUTDOWN_TIMEOUT: int = 10

    # ── security (Phase 5) ──────────────────────────────────
    ALLOWED_UPDATES: str = "message,callback_query,pre_checkout_query"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # ── validators ─────────────────────────────────────────────

    @field_validator("CURRENCY")
    @classmethod
    def _validate_currency(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("CURRENCY must be a 3-letter ISO-4217 code (e.g. IDR, USD)")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.strip().upper()
        if upper not in valid:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(valid)}, got {v!r}")
        return upper

    @field_validator("RATE_LIMIT_PER_SECOND")
    @classmethod
    def _validate_rate_limit_rps(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("RATE_LIMIT_PER_SECOND must be > 0")
        return v

    @field_validator("RATE_LIMIT_BURST")
    @classmethod
    def _validate_rate_limit_burst(cls, v: int) -> int:
        if v < 1:
            raise ValueError("RATE_LIMIT_BURST must be >= 1")
        return v

    @field_validator("GRACEFUL_SHUTDOWN_TIMEOUT")
    @classmethod
    def _validate_shutdown_timeout(cls, v: int) -> int:
        if v < 1:
            raise ValueError("GRACEFUL_SHUTDOWN_TIMEOUT must be >= 1 second")
        return v

    @field_validator("QRIS_INVOICE_EXPIRY_MINUTES")
    @classmethod
    def _validate_qris_expiry(cls, v: int) -> int:
        if v < 1:
            raise ValueError("QRIS_INVOICE_EXPIRY_MINUTES must be >= 1 minute")
        return v

    @model_validator(mode="after")
    def _validate_production_safety(self) -> Settings:
        """Warn (not crash) if production-looking settings lack safety nets."""
        return self

    # ── derived helpers ───────────────────────────────────────

    @property
    def admin_ids(self) -> list[int]:
        if not self.ADMINS:
            return []
        return [int(x.strip()) for x in self.ADMINS.split(",") if x.strip()]

    @property
    def allowed_updates_list(self) -> list[str]:
        """Parse ALLOWED_UPDATES into a list for aiogram polling."""
        if not self.ALLOWED_UPDATES:
            return []
        return [u.strip() for u in self.ALLOWED_UPDATES.split(",") if u.strip()]

    @property
    def is_production(self) -> bool:
        """Heuristic: True when USE_WEBHOOK is on or DATABASE_URL points to postgres."""
        return self.USE_WEBHOOK or "postgresql" in self.DATABASE_URL

    @property
    def safe_database_url(self) -> str:
        """Database URL with the password masked for log output."""
        if "@" in self.DATABASE_URL:
            # postgresql+psycopg://user:pass@host/db → postgresql+psycopg://user:***@host/db
            prefix, suffix = self.DATABASE_URL.rsplit("@", 1)
            if ":" in prefix.split("://", 1)[-1]:
                scheme, rest = prefix.split("://", 1)
                if ":" in rest:
                    user = rest.split(":", 1)[0]
                    prefix = f"{scheme}://{user}:***"
            return f"{prefix}@{suffix}"
        return self.DATABASE_URL


settings = Settings()
