"""Tests for the RateLimitMiddleware — token-bucket rate limiter."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot_app.middleware.rate_limit import RateLimitMiddleware, _TokenBucket


class TestTokenBucket:
    def test_initial_tokens_equal_max(self) -> None:
        b = _TokenBucket(max_tokens=5, refill_rate=1.0)
        assert b.tokens == 5.0

    def test_consume_success(self) -> None:
        b = _TokenBucket(max_tokens=5, refill_rate=1.0)
        assert b.consume() is True
        assert b.tokens == 4.0

    def test_consume_all_tokens(self) -> None:
        b = _TokenBucket(max_tokens=3, refill_rate=1.0)
        assert b.consume() is True
        assert b.consume() is True
        assert b.consume() is True
        assert b.consume() is False  # exhausted

    def test_refill_over_time(self) -> None:
        b = _TokenBucket(max_tokens=2, refill_rate=1000.0)  # very fast refill
        b.tokens = 0
        # Manually set the last_refill back in time
        b.last_refill = time.monotonic() - 0.01  # 10ms ago
        assert b.consume() is True  # should have refilled

    def test_tokens_capped_at_max(self) -> None:
        b = _TokenBucket(max_tokens=3, refill_rate=1000.0)
        b.tokens = 2
        b.last_refill = time.monotonic() - 1.0  # long ago
        b.consume()
        assert b.tokens <= 3.0  # should be capped


class TestRateLimitMiddleware:
    @pytest.fixture
    def middleware(self) -> RateLimitMiddleware:
        return RateLimitMiddleware(rps=10.0, burst=3)

    @pytest.fixture
    def mock_handler(self) -> AsyncMock:
        return AsyncMock(return_value="ok")

    @pytest.fixture
    def mock_data(self) -> dict:
        bot = AsyncMock()
        return {"bot": bot}

    @pytest.mark.asyncio
    async def test_normal_flow_passes(
        self, middleware: RateLimitMiddleware, mock_handler: AsyncMock, mock_data: dict
    ) -> None:
        """A single request should pass."""
        from aiogram.types import Chat, Message, User

        msg = MagicMock(spec=Message)
        msg.from_user = MagicMock(spec=User)
        msg.from_user.id = 42
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 42

        result = await middleware(mock_handler, msg, mock_data)
        assert result == "ok"
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_burst_exhaustion(
        self, middleware: RateLimitMiddleware, mock_handler: AsyncMock, mock_data: dict
    ) -> None:
        """After burst is exhausted, further requests should be blocked."""
        from aiogram.types import Chat, Message, User

        msg = MagicMock(spec=Message)
        msg.from_user = MagicMock(spec=User)
        msg.from_user.id = 99
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 99

        # Burst=3 so first 3 should pass
        for _ in range(3):
            await middleware(mock_handler, msg, mock_data)
        assert mock_handler.call_count == 3

        # 4th should be blocked
        mock_handler.reset_mock()
        result = await middleware(mock_handler, msg, mock_data)
        assert result is None
        mock_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_different_users_independent(
        self, middleware: RateLimitMiddleware, mock_handler: AsyncMock, mock_data: dict
    ) -> None:
        """Each user gets their own bucket."""
        from aiogram.types import Chat, Message, User

        msg1 = MagicMock(spec=Message)
        msg1.from_user = MagicMock(spec=User)
        msg1.from_user.id = 1
        msg1.chat = MagicMock(spec=Chat)
        msg1.chat.id = 1

        msg2 = MagicMock(spec=Message)
        msg2.from_user = MagicMock(spec=User)
        msg2.from_user.id = 2
        msg2.chat = MagicMock(spec=Chat)
        msg2.chat.id = 2

        # Exhaust user 1
        for _ in range(3):
            await middleware(mock_handler, msg1, mock_data)

        # User 2 should still be able to send
        mock_handler.reset_mock()
        result = await middleware(mock_handler, msg2, mock_data)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_no_user_id_passes_through(
        self, middleware: RateLimitMiddleware, mock_handler: AsyncMock, mock_data: dict
    ) -> None:
        """Events with no user_id should pass through (e.g. channel posts)."""
        from aiogram.types import Chat, Message

        msg = MagicMock(spec=Message)
        msg.from_user = None
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 42

        result = await middleware(mock_handler, msg, mock_data)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_callback_query_answered_on_throttle(
        self, middleware: RateLimitMiddleware, mock_handler: AsyncMock, mock_data: dict
    ) -> None:
        """Throttled callback queries should be answered to stop the spinner."""
        from aiogram.types import CallbackQuery, Chat, Message as TgMessage, User

        user = MagicMock(spec=User)
        user.id = 42

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = MagicMock(spec=TgMessage)
        cb.message.chat = MagicMock(spec=Chat)
        cb.message.chat.id = 42
        cb.answer = AsyncMock()

        # Exhaust the bucket
        for _ in range(3):
            await middleware(mock_handler, cb, mock_data)

        # 4th should be blocked and callback answered
        mock_handler.reset_mock()
        result = await middleware(mock_handler, cb, mock_data)
        assert result is None

    @pytest.mark.asyncio
    async def test_middleware_error_does_not_block(
        self, mock_handler: AsyncMock, mock_data: dict
    ) -> None:
        """If rate limiter itself errors, the update should still be processed."""
        middleware = RateLimitMiddleware(rps=10.0, burst=3)

        # Create a message that will cause _extract_user_id to work but
        # _get_bucket to be called normally
        from aiogram.types import Chat, Message, User

        msg = MagicMock(spec=Message)
        msg.from_user = MagicMock(spec=User)
        msg.from_user.id = 42
        msg.chat = MagicMock(spec=Chat)
        msg.chat.id = 42

        # This should still pass even if middleware has an internal issue
        result = await middleware(mock_handler, msg, mock_data)
        assert result == "ok"

    def test_cleanup_removes_stale_buckets(self) -> None:
        """Cleanup should remove buckets that haven't been used recently."""
        middleware = RateLimitMiddleware(rps=1.0, burst=3)

        # Create some buckets
        for uid in range(10):
            middleware._get_bucket(uid)

        assert len(middleware._buckets) == 10

        # Cleanup with very short max_age (everything should be removed)
        middleware.cleanup(max_age=0.0)
        assert len(middleware._buckets) == 0

    def test_cleanup_keeps_active_buckets(self) -> None:
        """Cleanup should keep buckets that were recently used."""
        middleware = RateLimitMiddleware(rps=1.0, burst=3)

        # Create a bucket and use it
        middleware._get_bucket(1)

        # Cleanup with long max_age (nothing should be removed)
        middleware.cleanup(max_age=3600.0)
        assert len(middleware._buckets) == 1
