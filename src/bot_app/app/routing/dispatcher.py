"""Custom low-level dispatcher for the gateway-based polling path.

When aiogram is driving the event loop (the default), this dispatcher is
not used.  It is kept for scenarios where the raw ``TelegramGateway`` is
used to pull updates.
"""

from __future__ import annotations

import logging

from ...shared.models.telegram import Update
from ...shared.protocols.telegram_gateway import TelegramGateway
from .command_registry import CommandRegistry
from .parser import parse_update

logger = logging.getLogger(__name__)


class Dispatcher:
    """Dispatch parsed commands to registered handlers."""

    def __init__(self, registry: CommandRegistry, gateway: TelegramGateway) -> None:
        self.registry = registry
        self.gateway = gateway

    async def dispatch(self, update: Update) -> None:
        try:
            command = parse_update(update)
            handler = self.registry.get_handler(command.name)
            if handler:
                await handler(command)
            else:
                await self.gateway.send_message(
                    command.chat_id,
                    f"Unknown command: {command.name}. Try /help",
                )
        except ValueError as exc:
            logger.debug("Skipping non-command update: %s", exc)
        except Exception as exc:
            logger.error("Error dispatching update: %s", exc)
