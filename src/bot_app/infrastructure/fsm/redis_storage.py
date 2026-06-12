"""Redis-backed FSM storage builder (aiogram 3 built-in).

Aiogram 3.x ships with ``aiogram.fsm.storage.redis.RedisStorage`` which
wraps ``redis.asyncio``.  No separate ``aiogram-fsm-storage-redis`` package
is needed.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from aiogram.fsm.storage.redis import RedisStorage


def build_redis_storage(url: str) -> RedisStorage:
    """Create a ``RedisStorage`` from a ``redis://`` URL."""
    redis_conn = aioredis.from_url(url)
    return RedisStorage(redis=redis_conn)
