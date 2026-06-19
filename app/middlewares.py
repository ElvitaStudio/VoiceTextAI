from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from app.database import Database


def telegram_profile(message: Message) -> tuple[
    int,
    str | None,
    str | None,
    str | None,
    str | None,
]:
    if message.from_user is None:
        raise ValueError("Message has no sender")
    user = message.from_user
    first_name = getattr(user, "first_name", None)
    last_name = getattr(user, "last_name", None)
    full_name = " ".join(
        part for part in (first_name, last_name) if part
    ) or None
    return (
        user.id,
        getattr(user, "username", None),
        first_name,
        last_name,
        full_name,
    )


class UserProfileMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        text = event.text or ""
        is_start = text.split(maxsplit=1)[0].split("@", 1)[0] == "/start"
        if event.from_user is not None and not event.from_user.is_bot and not is_start:
            db: Database | None = data.get("db")
            if db is not None:
                data["profile_user"] = await db.upsert_user(
                    *telegram_profile(event)
                )
        return await handler(event, data)
