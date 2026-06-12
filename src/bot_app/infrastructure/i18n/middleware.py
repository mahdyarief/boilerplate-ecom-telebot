"""Language middleware — auto-set user language from DB into handler data.

This middleware runs *after* dependency injection so that the
``session_factory`` is available.  It looks up the user's language
preference from the ``users`` table and injects ``lang`` into the
handler data dictionary.  If the user is not found, it falls back
to ``settings.LANGUAGE``.

Handlers can then call ``t(key, data["lang"])`` for translated strings.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, types

from ...core.config import settings
from ...infrastructure.persistence.uow import UnitOfWork

logger = logging.getLogger(__name__)


class LanguageMiddleware(BaseMiddleware):
    """Inject the user's language preference into handler data.

    After this middleware runs, ``data["lang"]`` contains the user's
    ISO-639-1 language code (e.g. ``"id"``, ``"en"``).
    """

    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Default to the global language setting
        lang = settings.LANGUAGE

        try:
            user_id = self._extract_user_id(event)
            session_factory = data.get("session_factory")

            if user_id is not None and session_factory is not None:
                async with UnitOfWork(session_factory) as uow:
                    user = await uow.users.get(user_id)
                    if user is not None:
                        lang = user.language
        except Exception as exc:
            logger.debug("language_middleware.fallback: %s", exc)

        data["lang"] = lang
        return await handler(event, data)

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
