"""boilerplate-ecom-telebot · core configuration (SSOT)."""

from __future__ import annotations

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # ── derived helpers ───────────────────────────────────────

    @property
    def admin_ids(self) -> list[int]:
        if not self.ADMINS:
            return []
        return [int(x.strip()) for x in self.ADMINS.split(",") if x.strip()]


settings = Settings()
