"""Entrypoint — choose polling or webhook mode from settings."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from .bootstrap import bootstrap
from .core.config import settings

logger = logging.getLogger(__name__)


async def _on_startup(bot, dp) -> None:
    if settings.USE_WEBHOOK:
        await bot.set_webhook(
            url=f"{settings.WEBHOOK_URL}{settings.WEBHOOK_PATH}",
            secret_token=settings.WEBHOOK_SECRET_TOKEN or None,
        )
        logger.info("webhook set: %s%s", settings.WEBHOOK_URL, settings.WEBHOOK_PATH)
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("polling mode")


async def main() -> None:
    logger.info(
        "starting bot",
        extra={
            "shop": settings.SHOP_NAME,
            "currency": settings.CURRENCY,
            "language": settings.LANGUAGE,
            "admins": len(settings.admin_ids),
            "webhook": settings.USE_WEBHOOK,
        },
    )

    bot, dp, engine = await bootstrap()

    if settings.USE_WEBHOOK:
        from aiogram.webhook.aiohttp_server import (
            SimpleRequestHandler,
            setup_application,
        )

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
        logger.info("server listening on %s:%s", settings.HOST, settings.PORT)
        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()
            await engine.dispose()
    else:
        await _on_startup(bot, dp)
        try:
            await dp.start_polling(bot)
        finally:
            await bot.session.close()
            await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
