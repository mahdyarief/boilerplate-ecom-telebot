"""Per-user token-bucket rate limiter middleware.

Uses a simple in-memory token-bucket algorithm.  When Redis is
available the counters can be shared across processes, but the default
in-memory implementation is sufficient for a single-process polling bot.

Phase 5 hardening: prevents individual users from flooding the bot
(whether accidental or malicious) and degrades gracefully — if the
rate limiter itself errors, the update is still processed.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, types

from ..core.config import settings
from ..core.logging import get_logger

logger = get_logger(__name__)


class _TokenBucket:
    """Token-bucket for a single user."""

    __slots__ = ("last_refill", "max_tokens", "refill_rate", "tokens")

    def __init__(self, max_tokens: int, refill_rate: float) -> None:
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate  # tokens per second
        self.tokens: float = max_tokens
        self.last_refill: float = time.monotonic()

    def consume(self) -> bool:
        """Try to consume one token.  Returns ``True`` if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class RateLimitMiddleware(BaseMiddleware):
    """Per-user rate limiter using token-bucket algorithm.

    Configuration via ``settings.RATE_LIMIT_PER_SECOND`` and
    ``settings.RATE_LIMIT_BURST``.

    When a user exceeds the rate limit they receive a short warning
    message and the update is **not** forwarded to the handler.
    """

    def __init__(
        self,
        *,
        rps: float | None = None,
        burst: int | None = None,
    ) -> None:
        self._rps = rps or settings.RATE_LIMIT_PER_SECOND
        self._burst = burst or settings.RATE_LIMIT_BURST
        self._buckets: dict[int, _TokenBucket] = {}
        logger.info(
            "rate_limit_middleware.initialized",
            rps=self._rps,
            burst=self._burst,
        )

    def _get_bucket(self, user_id: int) -> _TokenBucket:
        """Get or create a bucket for *user_id*."""
        bucket = self._buckets.get(user_id)
        if bucket is None:
            bucket = _TokenBucket(
                max_tokens=self._burst,
                refill_rate=self._rps,
            )
            self._buckets[user_id] = bucket
        return bucket

    def _extract_user_id(self, event: types.TelegramObject) -> int | None:
        """Best-effort extraction of user_id from any update type."""
        if isinstance(event, types.Message):
            return event.from_user.id if event.from_user else None
        if isinstance(event, types.CallbackQuery):
            return event.from_user.id if event.from_user else None
        if isinstance(event, types.PreCheckoutQuery):
            return event.from_user.id if event.from_user else None
        # Fallback for other update types
        from_user = getattr(event, "from_user", None) or getattr(event, "from", None)
        return from_user.id if from_user else None

    async def __call__(
        self,
        handler: Callable[[types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Rate-limit check before forwarding to the handler."""
        try:
            user_id = self._extract_user_id(event)
            if user_id is None:
                return await handler(event, data)

            bucket = self._get_bucket(user_id)
            if bucket.consume():
                return await handler(event, data)

            # Rate-limited
            logger.warning("rate_limit_middleware.throttled", user_id=user_id)

            # Try to notify the user
            chat_id = self._extract_chat_id(event)
            if chat_id is not None:
                try:
                    await data.get("bot", data.get("bot")).send_message(
                        chat_id=chat_id,
                        text="⚠️ Terlalu banyak permintaan. Tunggu sebentar ya!",
                    )
                except Exception:
                    pass  # best-effort notification

            # Answer callback queries to stop the loading spinner
            if isinstance(event, types.CallbackQuery):
                with contextlib.suppress(Exception):
                    await event.answer("⚠️ Tunggu sebentar…", show_alert=False)

            return None  # Do not propagate to the handler
        except Exception as exc:
            # Never block the bot if the rate limiter itself errors
            logger.error("rate_limit_middleware.error", error=str(exc))
            return await handler(event, data)

    def _extract_chat_id(self, event: types.TelegramObject) -> int | None:
        """Extract chat_id from the event for sending a warning message."""
        if isinstance(event, types.Message):
            return event.chat.id if event.chat else None
        if isinstance(event, types.CallbackQuery):
            return event.message.chat.id if event.message and event.message.chat else None
        if isinstance(event, types.PreCheckoutQuery):
            return None  # No chat in pre_checkout_query
        return None

    def cleanup(self, max_age: float = 3600.0) -> None:
        """Remove stale buckets that haven't been used recently.

        Call this periodically (e.g. every hour) to prevent unbounded
        memory growth in long-running bots.
        """
        now = time.monotonic()
        stale_keys = [
            uid
            for uid, bucket in self._buckets.items()
            if (now - bucket.last_refill) > max_age
        ]
        for key in stale_keys:
            del self._buckets[key]
        if stale_keys:
            logger.debug("rate_limit_middleware.cleanup", removed=len(stale_keys))
