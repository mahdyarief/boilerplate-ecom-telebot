"""Tests for the RequestIdMiddleware — structlog context binding."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import structlog

from bot_app.middleware.request_id import RequestIdMiddleware, _short_uuid


class TestShortUuid:
    def test_length(self) -> None:
        uid = _short_uuid()
        assert len(uid) == 8

    def test_hex_characters(self) -> None:
        uid = _short_uuid()
        assert all(c in "0123456789abcdef" for c in uid)

    def test_uniqueness(self) -> None:
        """Two calls should produce different IDs (with very high probability)."""
        ids = {_short_uuid() for _ in range(100)}
        assert len(ids) == 100  # all unique


class TestRequestIdMiddleware:
    @pytest.fixture
    def middleware(self) -> RequestIdMiddleware:
        return RequestIdMiddleware()

    @pytest.fixture
    def mock_handler(self) -> AsyncMock:
        return AsyncMock(return_value="ok")

    @pytest.fixture
    def mock_data(self) -> dict:
        return {}

    @pytest.mark.asyncio
    async def test_request_id_injected_into_data(
        self, middleware: RequestIdMiddleware, mock_handler: AsyncMock, mock_data: dict
    ) -> None:
        """request_id should be added to the handler data dict."""
        from aiogram.types import Message, User

        msg = MagicMock(spec=Message)
        msg.from_user = MagicMock(spec=User)
        msg.from_user.id = 42

        await middleware(mock_handler, msg, mock_data)

        assert "request_id" in mock_data
        assert len(mock_data["request_id"]) == 8

    @pytest.mark.asyncio
    async def test_handler_called(
        self, middleware: RequestIdMiddleware, mock_handler: AsyncMock, mock_data: dict
    ) -> None:
        """The handler should be called after the middleware."""
        from aiogram.types import Message, User

        msg = MagicMock(spec=Message)
        msg.from_user = MagicMock(spec=User)
        msg.from_user.id = 42

        result = await middleware(mock_handler, msg, mock_data)
        assert result == "ok"
        mock_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_contextvars_cleared_after_handler(
        self, middleware: RequestIdMiddleware, mock_handler: AsyncMock, mock_data: dict
    ) -> None:
        """Structlog contextvars should be cleared after the handler finishes."""
        from aiogram.types import Message, User

        msg = MagicMock(spec=Message)
        msg.from_user = MagicMock(spec=User)
        msg.from_user.id = 42

        # Bind something before the middleware runs
        structlog.contextvars.bind_contextvars(pre_existing="test")

        await middleware(mock_handler, msg, mock_data)

        # After middleware, contextvars should be cleared
        # (the middleware itself clears them in its finally block)
        ctx = structlog.contextvars.get_contextvars()
        # pre_existing should be gone because we clear_contextvars at the start
        assert "request_id" not in ctx

    @pytest.mark.asyncio
    async def test_user_id_bound_for_message(
        self, middleware: RequestIdMiddleware, mock_handler: AsyncMock, mock_data: dict
    ) -> None:
        """user_id should be bound to structlog context for messages."""
        from aiogram.types import CallbackQuery, Message, User

        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = MagicMock(spec=User)
        cb.from_user.id = 99

        # Use a handler that captures the contextvars
        captured: dict = {}

        async def capturing_handler(event, data):
            captured.update(structlog.contextvars.get_contextvars())
            return "ok"

        await middleware(capturing_handler, cb, mock_data)

        assert captured.get("user_id") == 99
        assert "request_id" in captured

    @pytest.mark.asyncio
    async def test_no_user_id_still_works(
        self, middleware: RequestIdMiddleware, mock_handler: AsyncMock, mock_data: dict
    ) -> None:
        """Events with no user_id should still get a request_id."""
        from aiogram.types import Message

        msg = MagicMock(spec=Message)
        msg.from_user = None

        await middleware(mock_handler, msg, mock_data)
        assert "request_id" in mock_data

    @pytest.mark.asyncio
    async def test_contextvars_cleared_on_exception(
        self, middleware: RequestIdMiddleware, mock_data: dict
    ) -> None:
        """Contextvars should be cleared even if the handler raises."""
        from aiogram.types import Message, User

        msg = MagicMock(spec=Message)
        msg.from_user = MagicMock(spec=User)
        msg.from_user.id = 42

        async def failing_handler(event, data):
            raise RuntimeError("test error")

        with pytest.raises(RuntimeError, match="test error"):
            await middleware(failing_handler, msg, mock_data)

        # Contextvars should still be cleared
        ctx = structlog.contextvars.get_contextvars()
        assert "request_id" not in ctx
