from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master


class UserMiddleware(BaseMiddleware):
    """Resolve Master (if any) by Telegram user id and attach to handler data.

    Client resolution is intentionally NOT done here — in a multi-master bot one
    tg_id may be a client of multiple masters, so client lookup must be scoped
    by master_id and performed at the service layer.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["master"] = None
        data["client"] = None  # kept for handler compatibility

        inner = event.event if isinstance(event, Update) else event
        tg_user = getattr(inner, "from_user", None)
        if tg_user is None:
            return await handler(event, data)

        session: AsyncSession = data["session"]

        master = await session.scalar(
            select(Master).where(Master.tg_id == tg_user.id)
        )
        if master is not None:
            data["master"] = master

        return await handler(event, data)
