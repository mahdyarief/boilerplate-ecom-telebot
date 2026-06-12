"""Redis-backed FSM storage builder (requires ``redis`` package)."""

from __future__ import annotations

import redis.asyncio as aioredis
from aiogram.fsm.storage.redis import RedisStorage


def build_redis_storage(url: str) -> RedisStorage:
    """Create a ``RedisStorage`` from a ``redis://`` URL."""
    redis_conn = aioredis.from_url(url)
    return RedisStorage(redis=redis_conn)
