# ADR-005: Phase 5 Hardening — Rate Limiting, Error Handling, and Observability

## Status
Accepted

## Context
Phases 0–4 delivered a functional shop bot but lacked production hardening:

1. **No rate limiting**: a single user could flood the bot with requests, exhausting
   handler capacity and database connections.
2. **No global error handler**: unhandled exceptions crashed the polling loop or
   left the user with no feedback. FSM states could become stuck.
3. **No request correlation**: structured logs had no way to link log entries
   belonging to the same user interaction.
4. **No graceful shutdown**: stopping the Docker container mid-flight could
   leave in-flight database transactions partially committed.
5. **Docker image lacked healthcheck** and was not multi-stage (dev tools in
   runtime image).

## Decision

### 1. Token-bucket rate limiter (`middleware/rate_limit.py`)
- Per-user in-memory token bucket.
- Configurable via `RATE_LIMIT_PER_SECOND` (refill rate) and `RATE_LIMIT_BURST`
  (maximum tokens).
- When a user is throttled they receive a brief message and callback queries
  are answered to dismiss the loading spinner.
- The middleware catches its own errors and never blocks the bot.

### 2. Global aiogram error handler (`middleware/error_handler.py`)
- Registers on `dp.errors` (the aiogram error router).
- Logs the full exception with structlog (including `request_id` from the
  middleware).
- Sends a user-friendly message (specific for `StockError`, generic for others).
- Answers callback queries and pre-checkout queries.
- Clears the FSM state to prevent stuck states.
- Optionally reports to Sentry when `SENTRY_DSN` is set.

### 3. Request-ID middleware (`middleware/request_id.py`)
- Generates a short UUID per update, binds it and `user_id` to structlog
  contextvars.
- All log entries produced during that update carry the same `request_id`.
- Clears contextvars in a `finally` block to prevent leakage.

### 4. Graceful shutdown (`main.py`)
- Installs SIGINT/SIGTERM signal handlers that set an `asyncio.Event`.
- In the `finally` block, properly closes the Bot API session and disposes of
  the SQLAlchemy engine.
- Webhook mode uses the same event for shutdown.

### 5. Docker hardening
- Multi-stage build: builder stage installs deps, runtime stage copies the
  venv only (no `uv` or build tools in production image).
- `HEALTHCHECK` verifies the app module can be imported.
- Non-root user (`appuser`, uid 1000).
- `docker-compose.yml`: healthchecks for all services, memory limits, no
  public ports by default (Postgres/Redis accessible only within the
  Docker network).

### 6. Config validators
- `CURRENCY` must be a 3-letter ISO-4217 code.
- `LOG_LEVEL` must be a recognised Python logging level.
- `RATE_LIMIT_PER_SECOND` must be > 0.
- `RATE_LIMIT_BURST` must be >= 1.
- `GRACEFUL_SHUTDOWN_TIMEOUT` must be >= 1.

## Consequences

### Positive
- Bot survives user floods without degradation.
- Unhandled exceptions are logged with context and reported to Sentry.
- Users always get feedback on errors.
- Logs can be traced per-request.
- Clean shutdown prevents database corruption.
- Docker image is smaller and safer.

### Negative
- In-memory rate limiter does not share state across processes (multiple bot
  instances would each have independent limits). A Redis-backed limiter can
  be added later.
- Token bucket is a simple algorithm — it won't perfectly shape traffic under
  extreme load. For adversarial protection, a WAF or reverse-proxy rate
  limiter is recommended.
- Sentry integration adds `sentry-sdk` as a dependency, even if unused.

## Alternatives Considered

1. **Redis-backed rate limiter**: adds operational complexity; deferred to
   Phase 6 when multi-process deployment is needed.
2. **aiogram's built-in ThrottlingMiddleware**: only works for commands, not
   callback queries; less configurable.
3. **No Sentry**: considered but the opt-in `SENTRY_DSN` approach ensures
   zero overhead when not configured.
