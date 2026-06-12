# Architecture

The Telegram Bot Boilerplate uses a **Feature-Based Modular Monolith** architecture. This ensures a clean separation of concerns and allows for easy scaling as the bot's functionality grows.

## Layer Boundaries

### 1. Runtime/Entry (`src/bot_app/main.py`)
- Responsible for process startup.
- Dependency injection/wiring.
- Graceful shutdown handling (SIGINT/SIGTERM) with signal handlers.
- `ALLOWED_UPDATES` filter to ignore unnecessary update types.

### 2. Application Layer (`src/bot_app/app/`)
- **Polling**: Orchestrates the update loop with Telegram.
- **Routing**: Parses incoming messages and dispatches them to the correct feature handler.
- **Services**: Contains business logic that coordinates multiple infrastructure components or features.

### 3. Shared Layer (`src/bot_app/shared/`)
- **Models**: Data structures (Pydantic) representing Telegram objects and internal command shapes.
- **Protocols**: Python `Protocol` definitions (interfaces) for repositories and gateways. This ensures the Application layer stays decoupled from specific implementations.

### 4. Infrastructure Layer (`src/bot_app/infrastructure/`)
- **Telegram Adapter**: Implements the HTTP communication with Telegram API.
- **Persistence**: Implements the SQLite/PostgreSQL storage, repository implementations, and migrations.
- **FSM**: Redis-backed FSM storage (with in-memory fallback).
- **i18n**: Internationalisation via aiogram-i18n + Fluent.
- **Payments**: Payment provider protocol.

### 5. Features Layer (`src/bot_app/features/`)
- Contains the actual bot command handlers.
- Organized by feature sets (e.g., `basic`, `catalog`, `cart`, `checkout`, `orders`, `payments`, `admin`).
- Handlers are thin and delegate to services or repositories.

### 6. Middleware Layer (`src/bot_app/middleware/`) — Phase 5
- **Request-ID**: Binds a unique correlation ID + user_id to structlog contextvars per update.
- **Rate Limit**: Per-user token-bucket rate limiter (configurable rps + burst).
- **Error Handler**: Global aiogram error handler that logs, notifies users, clears stuck FSMs, and reports to Sentry.

## Data Flow
1. **Poller** receives a raw update from **Telegram Gateway**.
2. **Request-ID Middleware** binds correlation ID to structlog.
3. **Rate Limit Middleware** checks if the user has exceeded their quota.
4. **Dependency Middleware** injects settings and session_factory.
5. **Dispatcher** passes the message to the feature **Router**.
6. **Handler** executes logic, potentially calling a **Service** or **Repository**.
7. **Handler** uses the **Bot** to send a response back to the user.
8. If any handler raises, the **Global Error Handler** catches it, logs, and notifies the user.

## Middleware Execution Order

Updates flow through middlewares outer → inner:

```
Request ID → Dependency Injection → Feature Router → Handler
```

Rate limiting is applied at the message/callback_query/pre_checkout_query level
(inner middleware), after dependency injection but before the handler.

Error handling wraps all of the above via `dp.errors`.
