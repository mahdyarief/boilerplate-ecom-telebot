"""FSM (Finite State Machine) storage configuration.

Uses Redis when ``REDIS_URL`` is set, otherwise falls back to aiogram's
in-memory storage (dev only).
"""

from __future__ import annotations

from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from ...core.config import settings

__all__ = ["create_fsm_storage"]


def create_fsm_storage() -> BaseStorage:
    """Return the appropriate FSM storage backend."""
    if settings.REDIS_URL:
        try:
            from aiogram.fsm.storage.redis import RedisStorage

            from .redis_storage import build_redis_storage

            return build_redis_storage(settings.REDIS_URL)
        except ImportError:
            import logging

            logging.getLogger(__name__).warning(
                "redis extra not installed — falling back to MemoryStorage"
            )

    return MemoryStorage()
