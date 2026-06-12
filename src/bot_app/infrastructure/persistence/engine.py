"""Database engine factory.  Creates the async SQLAlchemy engine from settings."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ...core.config import settings


def create_engine() -> AsyncEngine:
    """Build an ``AsyncEngine`` from ``settings.DATABASE_URL``."""
    return create_async_engine(
        settings.DATABASE_URL,
        echo=(settings.LOG_LEVEL.upper() == "DEBUG"),
    )
