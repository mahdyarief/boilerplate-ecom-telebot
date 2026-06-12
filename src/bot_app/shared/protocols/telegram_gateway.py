"""TelegramGateway protocol — abstract interface for Telegram API calls."""

from __future__ import annotations

from typing import List, Optional, Protocol

from ..models.telegram import Update


class TelegramGateway(Protocol):
    async def get_updates(self, offset: Optional[int] = None) -> List[Update]: ...
    async def send_message(self, chat_id: int, text: str) -> None: ...
    async def check_connection(self) -> bool: ...
    async def close(self) -> None: ...
