"""Global aiogram error handler — catches unhandled exceptions, logs, notifies.

Registers ``dp.errors`` handler that:

1. Logs the full exception with structlog (including request_id from middleware).
2. Sends a single user-friendly error message to the user.
3. Optionally reports to Sentry when ``SENTRY_DSN`` is set.

Phase 5 hardening: no unhandled exception should crash the bot or
leave the user staring at a blank screen.
"""

from __future__ import annotations

import contextlib

from aiogram import Router, types
from aiogram.fsm.context import FSMContext

from ..core.config import settings
from ..core.errors import BotError, StockError
from ..core.logging import get_logger

logger = get_logger(__name__)


async def _extract_chat_id(update: types.Update) -> int | None:
    """Get the best chat_id from the update for sending an error message."""
    if update.message:
        return update.message.chat.id
    if update.callback_query and update.callback_query.message:
        return update.callback_query.message.chat.id
    if update.pre_checkout_query:
        # pre_checkout queries are answered, not messaged
        return None
    return None


async def _send_user_error(bot: types.Bot, chat_id: int, text: str) -> None:
    """Send a user-friendly error message — best effort."""
    try:
        await bot.send_message(chat_id=chat_id, text=text)
    except Exception:
        pass  # never let the error handler itself raise


async def _answer_callback_safely(update: types.Update) -> None:
    """Answer a callback query to stop the loading spinner."""
    if update.callback_query:
        with contextlib.suppress(Exception):
            await update.callback_query.answer("❌ Terjadi kesalahan.", show_alert=True)


async def global_error_handler(
    update: types.Update,
    exception: Exception,
    bot: types.Bot,
    state: FSMContext | None = None,
) -> bool:
    """Handle all unhandled exceptions from aiogram handlers.

    Returns ``True`` to signal aiogram that the error was handled.
    """
    # ── 1. Structured logging ────────────────────────────
    logger.error(
        "unhandled_exception",
        error_type=type(exception).__name__,
        error_message=str(exception),
        update_id=update.update_id,
    )

    # ── 2. Sentry integration ────────────────────────────
    if settings.SENTRY_DSN:
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(exception)
        except ImportError:
            logger.warning("sentry_dsn_set_but_sentry_sdk_not_installed")
        except Exception as sentry_exc:
            logger.warning("sentry_capture_failed", error=str(sentry_exc))

    # ── 3. Clear FSM state on bot errors (avoid stuck FSMs) ─
    if state is not None:
        with contextlib.suppress(Exception):
            await state.clear()

    # ── 4. Answer callback queries ───────────────────────
    await _answer_callback_safely(update)

    # ── 5. User-friendly error message ──────────────────
    chat_id = await _extract_chat_id(update)
    if chat_id is not None:
        if isinstance(exception, StockError):
            text = "⚠️ Stok tidak cukup. Silakan coba lagi nanti."
        elif isinstance(exception, BotError):
            text = f"❌ {exception}"
        else:
            text = (
                "❌ Terjadi kesalahan internal. "
                "Tim kami telah diberitahu. Silakan coba lagi nanti."
            )
        await _send_user_error(bot, chat_id, text)

    # ── 6. Pre-checkout query must be answered ───────────
    if update.pre_checkout_query:
        with contextlib.suppress(Exception):
            await bot.answer_pre_checkout_query(
                pre_checkout_query_id=update.pre_checkout_query.id,
                ok=False,
                error_message="Terjadi kesalahan. Silakan coba lagi.",
            )

    return True  # error was handled


def register_error_handler(router: Router) -> None:
    """Register the global error handler on the given router (or dispatcher)."""
    router.errors.register(global_error_handler)
    logger.info("error_handler.registered")
