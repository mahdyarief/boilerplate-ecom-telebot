"""Long-polling runner using aiogram's built-in start_polling."""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher

logger = logging.getLogger(__name__)


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    """Start aiogram long-polling.  Blocks until stopped."""
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Starting long-polling…")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
