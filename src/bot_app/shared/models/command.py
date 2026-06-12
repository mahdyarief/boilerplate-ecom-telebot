"""Parsed command model (used by custom routing layer)."""

from __future__ import annotations

from pydantic import BaseModel


class Command(BaseModel):
    name: str
    args: list[str]
    raw_text: str
    chat_id: int
    update_id: int
