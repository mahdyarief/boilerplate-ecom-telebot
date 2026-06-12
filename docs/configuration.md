# Configuration

The bot's configuration is managed using **Pydantic Settings** with validators,
ensuring type safety, early error detection, and easy environment variable management.

## Environment Variables

The application reads settings from environment variables. A `.env` file can be
used for local development (copy `.env.example`).

### Core

| Variable | Description | Default |
|---|---|---|
| `BOT_TOKEN` | Your Telegram Bot Token (from @BotFather) | **Required** |
| `LOG_LEVEL` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `INFO` |
| `LANGUAGE` | Default user language | `id` |

### Shop

| Variable | Description | Default |
|---|---|---|
| `CURRENCY` | ISO-4217 3-letter currency code (validated) | `IDR` |
| `SHOP_NAME` | Display name of the shop | `Toko Saya` |
| `SHOP_SUPPORT_USERNAME` | Telegram username for support | `support` |

### Database

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy async connection string | `sqlite+aiosqlite:///data/bot.db` |

### Redis

| Variable | Description | Default |
|---|---|---|
| `REDIS_URL` | Redis URL for FSM storage. Empty = in-memory. | `redis://redis:6379/0` |

### Deployment

| Variable | Description | Default |
|---|---|---|
| `USE_WEBHOOK` | Use webhook mode instead of polling | `False` |
| `WEBHOOK_URL` | Public URL for webhook | — |
| `WEBHOOK_PATH` | Path suffix for webhook | `/webhook` |
| `WEBHOOK_SECRET_TOKEN` | Secret token to validate webhook requests | — |
| `HOST` | Bind host for webhook server | `0.0.0.0` |
| `PORT` | Bind port for webhook server | `8000` |

### Payments

| Variable | Description | Default |
|---|---|---|
| `PAYMENT_PROVIDERS` | Comma-separated payment provider list | `provider_token` |
| `PROVIDER_TOKEN` | Telegram Payments provider token | — |

### Rate Limiting (Phase 5)

| Variable | Description | Default |
|---|---|---|
| `RATE_LIMIT_PER_SECOND` | Token refill rate per user (tokens/second) | `1.0` |
| `RATE_LIMIT_BURST` | Maximum burst per user | `5` |

### Observability (Phase 5)

| Variable | Description | Default |
|---|---|---|
| `SENTRY_DSN` | Sentry DSN for error tracking (optional) | — |
| `ALLOWED_UPDATES` | Comma-separated update types to receive | `message,callback_query,pre_checkout_query` |

### Graceful Shutdown (Phase 5)

| Variable | Description | Default |
|---|---|---|
| `GRACEFUL_SHUTDOWN_TIMEOUT` | Seconds to wait for in-flight requests | `10` |

## Validators

The following settings have Pydantic field validators that raise on invalid values:

- **`CURRENCY`** — must be a 3-letter alphabetic ISO-4217 code (auto-uppercased).
- **`LOG_LEVEL`** — must be one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
- **`RATE_LIMIT_PER_SECOND`** — must be > 0.
- **`RATE_LIMIT_BURST`** — must be >= 1.
- **`GRACEFUL_SHUTDOWN_TIMEOUT`** — must be >= 1.

## SSOT Implementation

The `src/bot_app/core/config.py` module is the **only** place where environment
variables are accessed. All other modules must import settings from this central
location.

```python
from bot_app.core.config import settings

token = settings.BOT_TOKEN
rate = settings.RATE_LIMIT_PER_SECOND
```

### Derived Properties

| Property | Type | Description |
|---|---|---|
| `admin_ids` | `list[int]` | Parsed from comma-separated `ADMINS` |
| `allowed_updates_list` | `list[str]` | Parsed from `ALLOWED_UPDATES` |
| `is_production` | `bool` | `True` if `USE_WEBHOOK` or PostgreSQL URL |
| `safe_database_url` | `str` | Database URL with password masked for logs |
