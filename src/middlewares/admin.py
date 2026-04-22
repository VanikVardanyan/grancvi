from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.config import settings


class AdminMiddleware(BaseMiddleware):
    """Populate ``data['is_admin']`` based on ADMIN_TG_IDS env."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["is_admin"] = False

        inner = event.event if isinstance(event, Update) else event
        tg_user = getattr(inner, "from_user", None)
        if tg_user is not None and tg_user.id in settings.admin_tg_ids:
            data["is_admin"] = True

        return await handler(event, data)
