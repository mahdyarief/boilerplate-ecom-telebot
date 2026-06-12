# Configuration

The bot's configuration is managed using **Pydantic Settings**, ensuring type safety and easy environment variable management.

## Environment Variables
The application reads settings from environment variables. A `.env` file can be used for local development.

| Variable | Description | Default |
|---|---|---|
| `BOT_TOKEN` | Your Telegram Bot Token (from @BotFather) | **Required** |
| `DATABASE_URL` | Path to the SQLite database file | `data/bot.db` |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `POLLING_TIMEOUT` | Timeout for long polling in seconds | `30` |

## SSOT Implementation
The `src/bot_app/core/config.py` module is the **only** place where environment variables are accessed. All other modules must import settings from this central location.

```python
from bot_app.core.config import settings

token = settings.BOT_TOKEN
```
