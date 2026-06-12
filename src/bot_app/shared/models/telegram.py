"""Pydantic models for Telegram API objects (used by custom routing / gateway layer)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class User(BaseModel):
    id: int
    is_bot: bool = False
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None


class Chat(BaseModel):
    id: int
    type: str = "private"
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


class Message(BaseModel):
    message_id: int
    from_user: User | None = Field(None, alias="from")
    chat: Chat
    date: int = 0
    text: str | None = None


class Update(BaseModel):
    update_id: int
    message: Message | None = None


class UpdatesResponse(BaseModel):
    ok: bool
    result: list[Update]
