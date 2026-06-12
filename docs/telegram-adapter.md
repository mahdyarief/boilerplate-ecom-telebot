# Telegram Adapter

The Telegram Adapter handles all outgoing communication with the Telegram Bot API.

## Implementation
Located in `src/bot_app/infrastructure/telegram/http_gateway.py`, it uses the `httpx` library for efficient HTTP requests.

## Responsibilities
- Sending messages (`sendMessage`).
- Fetching updates (`getUpdates`).
- Error handling for Telegram API responses (e.g., handling rate limits or invalid tokens).

## Shared Models
Incoming Telegram payloads are parsed into Pydantic models defined in `src/bot_app/shared/models/telegram.py`. This ensures type safety and prevents "magic string" access to JSON objects.

```python
from bot_app.shared.models.telegram import Update

def handle_update(update: Update):
    chat_id = update.message.chat.id
    text = update.message.text
```
