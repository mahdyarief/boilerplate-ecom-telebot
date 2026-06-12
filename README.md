# boilerplate-ecom-telebot

> Production-ready **Telegram shop bot** boilerplate for Python.
> aiogram 3 · SQLAlchemy 2 (async) · PostgreSQL · Redis · i18n · Docker.

Designed for selling **physical or digital products** through a Telegram bot, with atomic stock handling, multiple payment providers, and an admin surface.

---

## ✨ Features

| | |
|---|---|
| 🛍️ | Product catalog with categories, images, stock |
| 🛒 | Per-user cart with quantity controls |
| 💳 | Pluggable payment gateway (provider token default, optional Telegram Stars) |
| 🔒 | **Race-condition-safe stock handling** (pessimistic lock + atomic decrement + idempotency) |
| 🌐 | i18n via `aiogram_i18n` + Fluent (id default, en, ru shipped) |
| 💱 | Money stored as integer smallest units (cents) per row, single currency per order |
| 👮 | Admin surface via bot commands + FSM (categories, products, orders, broadcast) |
| 🛡️ | **Per-user rate limiter** (token-bucket), request-ID correlation, global error handler |
| 📊 | Structured logging (structlog) + Sentry integration |
| 🚀 | Polling (default) and Webhook deployment modes |
| 🛑 | Graceful shutdown (SIGINT/SIGTERM) with engine.dispose() |
| 🐳 | One-command `make up` Docker Compose (bot + postgres + redis, healthchecks) |
| 🧪 | pytest + pytest-asyncio + coverage |
| 🧹 | ruff + mypy strict + pre-commit |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (or pip)
- Docker + Docker Compose (for the easy path)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A **payment provider token** if accepting fiat (IDR, RUB, USD, …). See [docs/payments.md](docs/payments.md).

### Option A — Docker (recommended)

```bash
cp .env.example .env
# fill in BOT_TOKEN, PROVIDER_TOKEN, ADMINS

make up         # builds + starts bot, postgres, redis
docker compose logs -f bot
```

### Option B — Local Python

```bash
uv venv .venv --python=3.12
uv pip install -e ".[dev]"

cp .env.example .env
# set DATABASE_URL to a local Postgres (or sqlite+aiosqlite:///data/bot.db for quick try)
# set REDIS_URL= (empty) to use in-memory FSM in dev

make migrate-up
make run
```

Send `/start` to your bot — you should see the welcome message.

---

## 🧱 Project Structure

```
src/bot_app/
├── main.py             # entry: polling or webhook, graceful shutdown
├── bootstrap.py        # wiring + DI registration + middleware
├── core/               # config (validators), logging, errors
├── shared/             # enums, money, DTOs, protocols
├── infrastructure/     # persistence, telegram, fsm, i18n, payments
├── middleware/          # request-id, rate-limit, error-handler (Phase 5)
├── app/                # cross-feature services, routing, polling
└── features/           # domain features (one folder per concern)
    ├── start/          # /start, /help, /lang
    ├── catalog/        # browse categories + products
    ├── cart/           # add/remove/qty
    ├── checkout/       # shipping → review → invoice
    ├── orders/         # user order history
    ├── payments/       # pre_checkout + successful_payment handlers
    └── admin/          # admin-gated CRUD + broadcast
```

See [docs/architecture.md](docs/architecture.md) for the full design.

---

## ⚙️ Configuration

All settings live in `.env` (see `.env.example`). Key values:

| Var | Default | Notes |
|---|---|---|
| `BOT_TOKEN` | — | from @BotFather |
| `CURRENCY` | `IDR` | ISO 4217, single-currency per bot |
| `LANGUAGE` | `id` | default user language |
| `DATABASE_URL` | `postgresql+psycopg://bot:bot@postgres:5432/bot` | any SQLAlchemy async URL |
| `REDIS_URL` | `redis://redis:6379/0` | empty = in-memory FSM (dev only) |
| `USE_WEBHOOK` | `False` | flip to `True` for production |
| `PAYMENT_PROVIDERS` | `provider_token` | comma-separated list |
| `PROVIDER_TOKEN` | — | from a Telegram Payments partner |
| `ADMINS` | — | comma-separated telegram user ids |
| `RATE_LIMIT_PER_SECOND` | `1.0` | tokens added per second per user |
| `RATE_LIMIT_BURST` | `5` | max burst per user |
| `SENTRY_DSN` | — | optional Sentry DSN for error tracking |
| `ALLOWED_UPDATES` | `message,callback_query,pre_checkout_query` | update types to receive |
| `GRACEFUL_SHUTDOWN_TIMEOUT` | `10` | seconds |

See [docs/configuration.md](docs/configuration.md) for the full reference.

---

## 🧪 Development

```bash
make check-imports   # quick sanity check
make lint            # ruff
make format          # ruff format
make type            # mypy strict
make test            # pytest with coverage
```

---

## 🗺️ Roadmap (this boilerplate)

- [x] **Phase 0** — Scaffolding (you are here)
- [ ] **Phase 1** — Domain & Persistence (User, Category, Product, Cart, Order, Payment models + Alembic)
- [ ] **Phase 2** — Catalog, cart, i18n
- [ ] **Phase 3** — Checkout + provider-token payments + stock-war protection
- [ ] **Phase 4** — Admin surface
- [x] **Phase 5** — Hardening (Redis FSM, structlog, Docker, error handlers, rate limiter)
- [ ] **Phase 6** — v1.1 (FastAPI admin panel, YooKassa, CryptoBot, discounts, webhooks)

See [PLAN.md](docs/PLAN.md) for the full implementation plan.

---

## 📜 License

MIT
