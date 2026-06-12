"""Request-ID middleware — binds a unique ID + user context to structlog.

Every incoming update gets a short UUID.  This ID is bound to the
structlog contextvars processor so that **all log lines** produced
while handling that update carry the same ``request_id`` — invaluable
for tracing a single user interaction through a dozen log entries.

Phase 5 hardening: structured-logging enrichment.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware, types

from ..core.logging import get_logger

logger = get_logger(__name__)


def _short_uuid() -> str:
    """Return a short (8-char) hex UUID for correlation."""
    return uuid.uuid4().hex[:8]


class RequestIdMiddleware(BaseMiddleware):
    """Bind ``request_id`` and ``user_id`` to structlog context for each update."""

    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        request_id = _short_uuid()
        data["request_id"] = request_id

        # Bind to structlog contextvars (picked up by merge_contextvars processor)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Also bind user_id if available
        user_id = self._extract_user_id(event)
        if user_id is not None:
            structlog.contextvars.bind_contextvars(user_id=user_id)

        logger.debug("request_id_middleware.start", request_id=request_id)
        try:
            return await handler(event, data)
        finally:
            structlog.contextvars.clear_contextvars()

    @staticmethod
    def _extract_user_id(event: types.TelegramObject) -> int | None:
        """Best-effort extraction of user_id from any update type."""
        if isinstance(event, types.Message):
            return event.from_user.id if event.from_user else None
        if isinstance(event, types.CallbackQuery):
            return event.from_user.id if event.from_user else None
        if isinstance(event, types.PreCheckoutQuery):
            return event.from_user.id if event.from_user else None
        from_user = getattr(event, "from_user", None) or getattr(event, "from", None)
        return from_user.id if from_user else None
