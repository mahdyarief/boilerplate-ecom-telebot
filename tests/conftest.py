"""Shared pytest fixtures for the test suite.

Every test that needs a database gets an in-memory SQLite async session
with tables created (and dropped) per test — no cross-test pollution.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot_app.infrastructure.persistence.models import Base

# ── Database fixtures ──────────────────────────────────────────


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide an in-memory SQLite async engine with all tables pre-created."""
    eng = create_async_engine("sqlite+aiosqlite://")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean ``AsyncSession`` bound to the test engine.

    The session is wrapped in a transaction that is rolled back after every
    test so the database stays pristine.
    """
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as sess:
        yield sess
        await sess.rollback()
