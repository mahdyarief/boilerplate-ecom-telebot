# Development Guide

## Prerequisites
- Python 3.10+
- `pip` or `poetry` (optional)

## Setup
1. Clone the repository.
2. Create a virtual environment: `python -m venv venv`.
3. Activate it:
   - Windows: `venv\Scripts\activate`
   - Unix/macOS: `source venv/bin/activate`
4. Install dependencies: `pip install -e .`.
5. Copy `.env.example` to `.env` and add your `BOT_TOKEN`.

## Running the Bot
```bash
python -m src.bot_app.main
```

## Code Quality
We use several tools to ensure high code quality:
- **Ruff**: For linting and formatting.
- **Mypy**: For static type checking.
- **Pytest**: For running unit and integration tests.

Run them before committing:
```bash
ruff check .
mypy src
pytest
```

## Structure Guidelines
- **Always use type hints**.
- **No business logic in handlers**; delegate to services.
- **Centralize configuration** in `core/config.py`.
- **Centralize command registration** in `routing/command_registry.py`.
