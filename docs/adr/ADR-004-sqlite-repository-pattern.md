# ADR-004: SQLite Repository Pattern

## Status
Accepted

## Context
The bot needs to persist data like user notes and its own state.

## Decision
We will use **SQLite** with the **Repository Pattern**.

## Rationale
- **Zero Configuration**: SQLite is built-in and requires no separate database server.
- **Performance**: Extremely efficient for the expected scale of a Telegram bot.
- **Decoupling**: The Repository Pattern (using Protocols) allows us to swap the storage implementation (e.g., to PostgreSQL or Redis) in the future without changing business logic.

## Consequences
- Database logic is confined to `src/bot_app/infrastructure/persistence/`.
- Services interact with storage through protocols defined in `src/bot_app/shared/protocols/`.
- Idempotent migrations will be used to manage the schema.
