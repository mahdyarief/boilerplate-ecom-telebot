# Persistence

The boilerplate uses **SQLite** for zero-dependency persistence, making it ideal for small-scale production and low-resource environments.

## Repository Pattern
We use the Repository Pattern to decouple business logic from the database implementation.

1. **Protocol**: Defined in `src/bot_app/shared/protocols/note_repository.py`.
2. **Implementation**: `src/bot_app/infrastructure/persistence/note_repository_sqlite.py`.

## Schema Management
Migrations are handled idempotently in `src/bot_app/infrastructure/persistence/migrations.py`. On startup, the bot ensures all necessary tables exist.

### Tables
- `state`: Stores global bot state, including `last_update_id` to ensure each message is processed exactly once.
- `notes`: Stores user-specific notes.
  - `id`: Autoincrement primary key.
  - `chat_id`: The ID of the chat/user.
  - `text`: The note content.
  - `created_at`: Timestamp (UTC).

## Thread Safety
The SQLite client in `src/bot_app/infrastructure/persistence/sqlite_client.py` ensures that connections are handled safely within the application's lifecycle.
