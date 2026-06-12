# Architecture

The Telegram Bot Boilerplate uses a **Feature-Based Modular Monolith** architecture. This ensures a clean separation of concerns and allows for easy scaling as the bot's functionality grows.

## Layer Boundaries

### 1. Runtime/Entry (`src/bot_app/main.py`)
- Responsible for process startup.
- Dependency injection/wiring.
- Graceful shutdown handling (SIGINT/SIGTERM).

### 2. Application Layer (`src/bot_app/app/`)
- **Polling**: Orchestrates the update loop with Telegram.
- **Routing**: Parses incoming messages and dispatches them to the correct feature handler.
- **Services**: Contains business logic that coordinates multiple infrastructure components or features.

### 3. Shared Layer (`src/bot_app/shared/`)
- **Models**: Data structures (Pydantic) representing Telegram objects and internal command shapes.
- **Protocols**: Python `Protocol` definitions (interfaces) for repositories and gateways. This ensures the Application layer stays decoupled from specific implementations.

### 4. Infrastructure Layer (`src/bot_app/infrastructure/`)
- **Telegram Adapter**: Implements the HTTP communication with Telegram API.
- **Persistence**: Implements the SQLite storage, repository implementations, and migrations.

### 5. Features Layer (`src/bot_app/features/`)
- Contains the actual bot command handlers.
- Organized by feature sets (e.g., `basic`, `notes`).
- Handlers are thin and delegate to services or repositories.

## Data Flow
1. **Poller** receives a raw update from **Telegram Gateway**.
2. **Dispatcher** passes the message to the **Parser**.
3. **Parser** creates a `Command` model.
4. **Dispatcher** looks up the handler in the **Registry**.
5. **Handler** executes logic, potentially calling a **Service** or **Repository**.
6. **Handler** uses the **Telegram Gateway** to send a response back to the user.
