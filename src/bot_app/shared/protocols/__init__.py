"""Protocol definitions — interfaces that infrastructure must implement."""

from __future__ import annotations

from .telegram_gateway import TelegramGateway

__all__ = ["TelegramGateway"]
