"""Error taxonomy — SSOT for exception classes."""

from __future__ import annotations


class BotError(Exception):
    """Base exception for the bot."""


class TelegramAPIError(BotError):
    """Raised when the Telegram API returns an error."""


class PersistenceError(BotError):
    """Raised when a database operation fails."""


class CommandParsingError(BotError):
    """Raised when a command cannot be parsed."""


class PaymentError(BotError):
    """Raised when a payment operation fails."""


class StockError(BotError):
    """Raised when stock cannot be reserved / decremented."""


class NotFoundError(BotError):
    """Raised when a requested resource does not exist."""
