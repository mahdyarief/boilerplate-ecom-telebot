"""Bootstrap — wire up bot, dispatcher, storage, middleware.

Phase 5 hardening: registers rate-limit, request-id, and global error
handler middlewares.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from .core.config import settings
from .core.logging import setup_logging
from .features.admin.router import router as admin_router
from .features.basic.handlers import router as basic_router
from .features.cart.router import router as cart_router
from .features.catalog.router import router as catalog_router
from .features.checkout.router import router as checkout_router
from .features.orders.router import router as orders_router
from .features.payments.router import router as payments_router
from .features.start.router import router as start_router
from .features.wallet.router import router as wallet_router
from .infrastructure.fsm.redis_storage import build_redis_storage
from .infrastructure.i18n import LanguageMiddleware
from .infrastructure.persistence.engine import create_engine, create_session_factory
from .middleware.error_handler import register_error_handler
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.request_id import RequestIdMiddleware

logger = logging.getLogger(__name__)


def _select_storage() -> BaseStorage:
    """Pick FSM storage: Redis if REDIS_URL set, otherwise in-memory."""
    if settings.REDIS_URL:
        logger.info("fsm storage: redis (%s)", settings.REDIS_URL)
        return build_redis_storage(settings.REDIS_URL)
    logger.info("fsm storage: in-memory (REDIS_URL not set)")
    return MemoryStorage()


class DependencyMiddleware(BaseMiddleware):
    """Inject ``settings`` and ``session_factory`` into every handler call."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["settings"] = settings
        data["session_factory"] = self.session_factory
        return await handler(event, data)


async def bootstrap() -> tuple[Bot, Dispatcher, AsyncEngine]:
    """Wire all components and return (bot, dispatcher, engine)."""
    setup_logging()

    # ── database ────────────────────────────────────────────
    engine: AsyncEngine = create_engine()
    session_factory = create_session_factory(engine)

    logger.info(
        "database engine created (%s)",
        settings.safe_database_url,
    )
    logger.info("run `alembic upgrade head` to apply migrations before starting the bot")

    # ── aiogram ─────────────────────────────────────────────
    storage = _select_storage()
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=storage)

    # ── Routers (order matters: start first so /start always works) ──
    dp.include_router(start_router)
    dp.include_router(catalog_router)
    dp.include_router(cart_router)
    dp.include_router(checkout_router)
    dp.include_router(orders_router)
    dp.include_router(payments_router)
    dp.include_router(wallet_router)
    dp.include_router(admin_router)
    dp.include_router(basic_router)

    # ── Middlewares (outermost → innermost) ────────────────
    # 1. Request-ID (binds request_id + user_id to structlog)
    dp.update.outer_middleware(RequestIdMiddleware())

    # 2. Dependency injection (settings + session_factory)
    dp.update.outer_middleware(DependencyMiddleware(session_factory))

    # 3. Language detection (injects user's lang into handler data)
    dp.update.outer_middleware(LanguageMiddleware())

    # 4. Rate limiting (token-bucket per user)
    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    dp.pre_checkout_query.middleware(RateLimitMiddleware())

    # ── Global error handler ───────────────────────────────
    register_error_handler(dp)

    # ── Sentry init (if DSN provided) ────────────────────
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=settings.SENTRY_DSN,
                traces_sample_rate=0.1,
            )
            logger.info("sentry.initialized")
        except ImportError:
            logger.warning("sentry_dsn_set_but_sentry_sdk_not_installed")

    return bot, dp, engine
