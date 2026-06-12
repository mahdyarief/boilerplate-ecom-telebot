"""Database engine factory and session helpers."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ...core.config import settings


def create_engine(url: str | None = None) -> AsyncEngine:
    """Build an :class:`AsyncEngine` from *url* or ``settings.DATABASE_URL``."""
    database_url = url or settings.DATABASE_URL
    return create_async_engine(
        database_url,
        echo=(settings.LOG_LEVEL.upper() == "DEBUG"),
    )


def create_session_factory(
    engine: AsyncEngine | None = None,
) -> async_sessionmaker[AsyncSession]:
    """Return an :class:`async_sessionmaker` bound to *engine*.

    If *engine* is ``None`` a fresh one is created from settings.
    """
    if engine is None:
        engine = create_engine()
    return async_sessionmaker(engine, expire_on_commit=False)
