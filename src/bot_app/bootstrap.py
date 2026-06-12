"""Bootstrap — wire up bot, dispatcher, storage, middleware."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.fsm.storage.base import StorageBase
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from .core.config import settings
from .core.logging import setup_logging
from .features.basic.handlers import router as basic_router
from .features.start.router import router as start_router
from .infrastructure.fsm.redis_storage import build_redis_storage
from .infrastructure.persistence.engine import create_engine
from .infrastructure.persistence.models import Base

logger = logging.getLogger(__name__)


def _select_storage() -> StorageBase:
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
    setup_logging(settings.LOG_LEVEL)

    # ── database ────────────────────────────────────────────
    engine: AsyncEngine = create_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Stub table creation — real schema is owned by Alembic migrations (Phase 1).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ── aiogram ─────────────────────────────────────────────
    storage = _select_storage()
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher(storage=storage)

    # Routers (order matters: start first so /start always works)
    dp.include_router(start_router)
    dp.include_router(basic_router)

    # Middleware
    dp.update.outer_middleware(DependencyMiddleware(session_factory))

    return bot, dp, engine
