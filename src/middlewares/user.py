from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master


class UserMiddleware(BaseMiddleware):
    """Resolve Master or Client by Telegram user id and attach to handler data.

    Requires `data["session"]` — DbSessionMiddleware must be registered first.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["master"] = None
        data["client"] = None

        tg_user = getattr(event, "from_user", None)
        if tg_user is None:
            return await handler(event, data)

        session: AsyncSession = data["session"]

        master = await session.scalar(select(Master).where(Master.tg_id == tg_user.id))
        if master is not None:
            data["master"] = master
            return await handler(event, data)

        client = await session.scalar(select(Client).where(Client.tg_id == tg_user.id))
        if client is not None:
            data["client"] = client

        return await handler(event, data)
