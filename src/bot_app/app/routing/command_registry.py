"""Command registry — SSOT for command name → handler → description mapping.

Used by the custom low-level routing layer.  Aiogram routers use their
own registration, but this registry provides the ``/help`` text and a
central place to list all commands.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

HandlerFunc = Callable[..., Awaitable[None]]


@dataclass
class CommandMetadata:
    name: str
    description: str
    handler: HandlerFunc


class CommandRegistry:
    """Mutable registry of bot commands."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandMetadata] = {}

    def register(self, name: str, description: str, handler: HandlerFunc) -> None:
        self._commands[name] = CommandMetadata(name, description, handler)

    def get_handler(self, name: str) -> HandlerFunc | None:
        meta = self._commands.get(name)
        return meta.handler if meta else None

    def get_all_metadata(self) -> list[CommandMetadata]:
        return list(self._commands.values())
