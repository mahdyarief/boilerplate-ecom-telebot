"""HTTP Telegram gateway — low-level Bot API client.

In production this module is largely superseded by aiogram's ``Bot`` class,
but it is retained for the custom polling / routing layer and as a
reference implementation of the ``TelegramGateway`` protocol.
"""

from __future__ import annotations

import logging

import aiohttp

from ...core.config import settings
from ...core.errors import TelegramAPIError
from ...shared.models.telegram import Update, UpdatesResponse
from ...shared.protocols.telegram_gateway import TelegramGateway

logger = logging.getLogger(__name__)


class HttpTelegramGateway(TelegramGateway):
    """Implements ``TelegramGateway`` using raw HTTP calls via ``aiohttp``."""

    def __init__(self) -> None:
        self._base_url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}"
        self._session: aiohttp.ClientSession | None = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=settings.POLLING_TIMEOUT + 10)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def get_updates(self, offset: int | None = None) -> list[Update]:
        params: dict = {"timeout": settings.POLLING_TIMEOUT}
        if offset is not None:
            params["offset"] = offset

        try:
            async with self.session.get(f"{self._base_url}/getUpdates", params=params) as resp:
                resp.raise_for_status()
                data = UpdatesResponse.model_validate(await resp.json())
                return data.result
        except Exception as exc:
            logger.error("get_updates failed: %s", exc)
            raise TelegramAPIError(f"getUpdates failed: {exc}") from exc

    async def send_message(self, chat_id: int, text: str) -> None:
        payload: dict = {"chat_id": chat_id, "text": text}
        try:
            async with self.session.post(f"{self._base_url}/sendMessage", json=payload) as resp:
                resp.raise_for_status()
        except Exception as exc:
            logger.error("send_message failed: %s", exc)
            raise TelegramAPIError(f"sendMessage failed: {exc}") from exc

    async def check_connection(self) -> bool:
        try:
            async with self.session.get(f"{self._base_url}/getMe") as resp:
                return resp.status == 200
        except Exception:
            return False

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
