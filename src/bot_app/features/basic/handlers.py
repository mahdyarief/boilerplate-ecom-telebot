"""/ping and /echo command handlers."""

from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

router = Router(name="basic")


@router.message(Command("ping"))
async def cmd_ping(message: types.Message) -> None:
    """Health-check command."""
    await message.answer("pong 🏓")


@router.message(Command("echo"))
async def cmd_echo(message: types.Message) -> None:
    """Echo back whatever follows /echo."""
    text = message.text
    if text is None:
        return
    parts = text.split(maxsplit=1)
    reply = parts[1] if len(parts) > 1 else "💤 Nothing to echo."
    await message.answer(reply)
