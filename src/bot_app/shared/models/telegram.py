"""Pydantic models for Telegram API objects (used by custom routing / gateway layer)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class User(BaseModel):
    id: int
    is_bot: bool = False
    first_name: str = ""
    last_name: Optional[str] = None
    username: Optional[str] = None


class Chat(BaseModel):
    id: int
    type: str = "private"
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None


class Message(BaseModel):
    message_id: int
    from_user: Optional[User] = Field(None, alias="from")
    chat: Chat
    date: int = 0
    text: Optional[str] = None


class Update(BaseModel):
    update_id: int
    message: Optional[Message] = None


class UpdatesResponse(BaseModel):
    ok: bool
    result: List[Update]
