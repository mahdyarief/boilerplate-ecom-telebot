"""Parse a raw Telegram Update into a Command model."""

from __future__ import annotations

from ...shared.models.command import Command
from ...shared.models.telegram import Update


def parse_update(update: Update) -> Command:
    if not update.message or not update.message.text:
        raise ValueError("Update contains no message text")

    text = update.message.text
    parts = text.split(" ", 1)
    name = parts[0].lower().strip()
    args = parts[1].split() if len(parts) > 1 else []
    raw_text = parts[1].strip() if len(parts) > 1 else ""

    return Command(
        name=name,
        args=args,
        raw_text=raw_text,
        chat_id=update.message.chat.id,
        update_id=update.update_id,
    )
