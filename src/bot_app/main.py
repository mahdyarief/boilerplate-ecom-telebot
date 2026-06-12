"""Entrypoint — choose polling or webhook mode, with graceful shutdown.

Phase 5 hardening:
- SIGINT / SIGTERM signal handlers for orderly teardown
- Scoped ``engine.dispose()`` and ``bot.session.close()`` in ``finally``
- ALLOWED_UPDATES filter to reduce unnecessary update processing
- Structured logging of startup / shutdown events
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from types import FrameType

from aiohttp import web

from .bootstrap import bootstrap
from .core.config import settings
from .core.logging import get_logger

logger = get_logger(__name__)

# ── Module-level references for signal handlers ─────────
_shutdown_event: asyncio.Event | None = None
_bot_ref = None
_engine_ref = None


def _signal_handler(signum: int, frame: FrameType | None) -> None:
    """Handle SIGINT / SIGTERM by setting the shutdown event."""
    sig_name = signal.Signals(signum).name
    logger.info("signal.received", signal=sig_name)
    if _shutdown_event is not None:
        _shutdown_event.set()


async def _on_startup(bot, dp) -> None:
    if settings.USE_WEBHOOK:
        await bot.set_webhook(
            url=f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}",
            secret_token=settings.WEBHOOK_SECRET_TOKEN or None,
            allowed_updates=settings.allowed_updates_list,
        )
        logger.info("webhook.set", url=f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}")
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("polling.mode")


async def _graceful_shutdown(bot, engine) -> None:
    """Orderly teardown: close bot session, dispose DB engine."""
    logger.info("shutdown.starting")

    try:
        # Close Bot API session
        if bot and bot.session:
            await bot.session.close()
            logger.info("shutdown.bot_session.closed")
    except Exception as exc:
        logger.error("shutdown.bot_session.error", error=str(exc))

    try:
        # Dispose of the async engine (closes all pool connections)
        if engine:
            await engine.dispose()
            logger.info("shutdown.engine.disposed")
    except Exception as exc:
        logger.error("shutdown.engine.error", error=str(exc))

    logger.info("shutdown.complete")


async def main() -> None:
    global _shutdown_event, _bot_ref, _engine_ref

    logger.info(
        "startup",
        shop=settings.SHOP_NAME,
        currency=settings.CURRENCY,
        language=settings.LANGUAGE,
        admins=len(settings.admin_ids),
        webhook=settings.USE_WEBHOOK,
        production=settings.is_production,
    )

    bot, dp, engine = await bootstrap()
    _bot_ref = bot
    _engine_ref = engine

    if settings.USE_WEBHOOK:
        from aiogram.webhook.aiohttp_server import (
            SimpleRequestHandler,
            setup_application,
        )

        _shutdown_event = asyncio.Event()

        app = web.Application()
        SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=settings.WEBHOOK_SECRET_TOKEN or None,
        ).register(app, path=settings.WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, settings.HOST, settings.PORT)
        await _on_startup(bot, dp)
        await site.start()
        logger.info("server.listening", host=settings.HOST, port=settings.PORT)

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler, sig, None)

        try:
            await _shutdown_event.wait()
        finally:
            await runner.cleanup()
            await _graceful_shutdown(bot, engine)
    else:
        _shutdown_event = asyncio.Event()

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler, sig, None)

        await _on_startup(bot, dp)

        try:
            await dp.start_polling(
                bot,
                allowed_updates=settings.allowed_updates_list,
            )
        finally:
            await _graceful_shutdown(bot, engine)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
