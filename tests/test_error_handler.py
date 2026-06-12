"""Tests for the global error handler middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiogram.types import (
    CallbackQuery,
    Chat,
    Message,
    PreCheckoutQuery,
    Update,
    User,
)

from bot_app.core.errors import BotError, StockError
from bot_app.middleware.error_handler import global_error_handler


def _make_update_with_message(user_id: int = 42, chat_id: int = 42) -> Update:
    """Create an Update with a Message for testing."""
    return Update(
        update_id=1,
        message=Message(
            message_id=1,
            date=0,
            chat=Chat(id=chat_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name="Test"),
            text="/test",
        ),
    )


def _make_update_with_callback(user_id: int = 42) -> Update:
    """Create an Update with a CallbackQuery for testing."""
    return Update(
        update_id=2,
        callback_query=CallbackQuery(
            id="cb1",
            from_user=User(id=user_id, is_bot=False, first_name="Test"),
            chat_instance="test",
            data="test:data",
            message=Message(
                message_id=1,
                date=0,
                chat=Chat(id=user_id, type="private"),
                from_user=User(id=user_id, is_bot=False, first_name="Test"),
            ),
        ),
    )


def _make_update_with_pre_checkout(user_id: int = 42) -> Update:
    """Create an Update with a PreCheckoutQuery for testing."""
    return Update(
        update_id=3,
        pre_checkout_query=PreCheckoutQuery(
            id="pc1",
            from_user=User(id=user_id, is_bot=False, first_name="Test"),
            currency="IDR",
            total_amount=50000,
            invoice_payload="1",
        ),
    )


class TestGlobalErrorHandler:
    @pytest.mark.asyncio
    async def test_generic_exception(self) -> None:
        """Generic exceptions should send a user-friendly message."""
        bot = AsyncMock()
        update = _make_update_with_message()

        result = await global_error_handler(
            update=update,
            exception=RuntimeError("something broke"),
            bot=bot,
        )

        assert result is True
        bot.send_message.assert_called_once()
        msg = bot.send_message.call_args[1]["text"]
        assert "kesalahan internal" in msg.lower() or "❌" in msg

    @pytest.mark.asyncio
    async def test_bot_error_sends_readable_message(self) -> None:
        """BotError subclasses should send their message."""
        bot = AsyncMock()
        update = _make_update_with_message()

        result = await global_error_handler(
            update=update,
            exception=BotError("Custom bot error"),
            bot=bot,
        )

        assert result is True
        msg = bot.send_message.call_args[1]["text"]
        assert "Custom bot error" in msg

    @pytest.mark.asyncio
    async def test_stock_error_sends_specific_message(self) -> None:
        """StockError should send a specific stock-related message."""
        bot = AsyncMock()
        update = _make_update_with_message()

        result = await global_error_handler(
            update=update,
            exception=StockError("Not enough stock"),
            bot=bot,
        )

        assert result is True
        msg = bot.send_message.call_args[1]["text"]
        assert "stok" in msg.lower() or "Stok" in msg

    @pytest.mark.asyncio
    async def test_callback_query_answered(self) -> None:
        """Callback queries should be answered on error."""
        bot = AsyncMock()
        user = User(id=42, is_bot=False, first_name="Test")
        chat = Chat(id=42, type="private")
        msg = Message(message_id=1, date=0, chat=chat, from_user=user, text="test")

        # Use MagicMock with an AsyncMock answer method
        cb = MagicMock(spec=CallbackQuery)
        cb.from_user = user
        cb.message = msg
        cb.answer = AsyncMock()

        update = Update(update_id=2, callback_query=cb)

        result = await global_error_handler(
            update=update,
            exception=RuntimeError("test"),
            bot=bot,
        )

        assert result is True
        # The callback query should be answered
        cb.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_checkout_answered_on_error(self) -> None:
        """Pre-checkout queries must be answered ok=False on error."""
        bot = AsyncMock()
        update = _make_update_with_pre_checkout()

        result = await global_error_handler(
            update=update,
            exception=RuntimeError("test"),
            bot=bot,
        )

        assert result is True
        bot.answer_pre_checkout_query.assert_called_once()
        call_kwargs = bot.answer_pre_checkout_query.call_args[1]
        assert call_kwargs["ok"] is False

    @pytest.mark.asyncio
    async def test_fsm_state_cleared_on_error(self) -> None:
        """FSM state should be cleared when an error occurs."""
        bot = AsyncMock()
        update = _make_update_with_message()
        state = AsyncMock()

        result = await global_error_handler(
            update=update,
            exception=RuntimeError("test"),
            bot=bot,
            state=state,
        )

        assert result is True
        state.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_true(self) -> None:
        """The handler should return True to mark the error as handled."""
        bot = AsyncMock()
        update = _make_update_with_message()

        result = await global_error_handler(
            update=update,
            exception=RuntimeError("test"),
            bot=bot,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_send_message_failure_does_not_raise(self) -> None:
        """If send_message itself fails, the handler should not raise."""
        bot = AsyncMock()
        bot.send_message.side_effect = RuntimeError("network error")
        update = _make_update_with_message()

        # Should NOT raise
        result = await global_error_handler(
            update=update,
            exception=RuntimeError("original error"),
            bot=bot,
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_no_chat_id_does_not_crash(self) -> None:
        """Updates without a chat_id should not crash the handler."""
        bot = AsyncMock()
        update = _make_update_with_pre_checkout()

        # Pre-checkout queries don't have a chat_id for messaging
        result = await global_error_handler(
            update=update,
            exception=RuntimeError("test"),
            bot=bot,
        )

        assert result is True
        # send_message should not be called for pre_checkout without chat
        # (but answer_pre_checkout_query should)

    @pytest.mark.asyncio
    async def test_sentry_capture_when_dsn_set(self) -> None:
        """When SENTRY_DSN is set, exceptions should be reported to Sentry."""
        bot = AsyncMock()
        update = _make_update_with_message()

        with patch("bot_app.middleware.error_handler.settings") as mock_settings:
            mock_settings.SENTRY_DSN = "https://test@sentry.io/123"
            with patch("sentry_sdk.capture_exception") as mock_capture:
                result = await global_error_handler(
                    update=update,
                    exception=RuntimeError("test"),
                    bot=bot,
                )

                assert result is True
                mock_capture.assert_called_once()
