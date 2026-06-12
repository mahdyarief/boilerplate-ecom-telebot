# Development Guide

## Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Docker + Docker Compose (for the full stack)

## Setup
1. Clone the repository.
2. Create a virtual environment: `uv venv .venv --python=3.12`.
3. Activate it:
   - Windows: `.venv\Scripts\activate`
   - Unix/macOS: `source .venv/bin/activate`
4. Install dependencies: `uv pip install -e ".[dev]"`.
5. Install pre-commit hooks: `pre-commit install`.
6. Copy `.env.example` to `.env` and add your `BOT_TOKEN`.

## Running the Bot
```bash
make run          # polling mode (default)
make run-webhook  # webhook mode (requires WEBHOOK_URL)
make up           # full Docker stack (bot + postgres + redis)
```

## Code Quality

We use several tools to ensure high code quality:

| Tool | Purpose | Command |
|---|---|---|
| ruff | Lint + format | `make lint` / `make format` |
| mypy | Type checking (strict) | `make type` |
| pytest | Unit + integration tests | `make test` |
| pre-commit | Git hook quality gate | `make install-hooks` |

Run the full quality gate before committing:
```bash
make lint && make type && make test
```

## Middleware System (Phase 5)

Middlewares execute in this order (outer → inner):

1. **Request-ID** — binds `request_id` + `user_id` to structlog contextvars
2. **Dependency Injection** — injects `settings` and `session_factory` into handler data
3. **Rate Limit** — per-user token-bucket (messages, callbacks, pre-checkout only)

The global **error handler** catches all unhandled exceptions, logs them,
notifies the user, clears stuck FSM states, and optionally reports to Sentry.

## Structure Guidelines
- **Always use type hints**.
- **No business logic in handlers**; delegate to services.
- **Centralize configuration** in `core/config.py` (Pydantic validators).
- **Use `UnitOfWork` for all database transactions** — never manage sessions manually.
- **Raise domain exceptions** (`BotError` subclasses) from services, not infrastructure leaks.
- **Log with structlog** via `get_logger(__name__)` — never use `print()`.
- **Never commit `.env`** — `detect-private-key` pre-commit hook guards against this.

## Docker

```bash
make up          # build + start stack
make down        # stop stack
make logs        # tail bot logs
make healthcheck # verify container health
```

The Docker image uses a multi-stage build. The healthcheck runs
`scripts/healthcheck.py` which verifies module imports. Set
`HEALTHCHECK_DB=1` to also verify database connectivity.
