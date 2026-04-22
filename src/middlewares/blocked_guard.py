from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Final

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.strings import strings

_ALLOWED_TEXTS: Final[frozenset[str]] = frozenset({"/start", "/cancel"})


class BlockedMasterGuardMiddleware(BaseMiddleware):
    """Reject all master-scope actions when master.blocked_at is set, showing a banner.

    Allowlist: /start and /cancel so user can at least exit the locked state.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        master = data.get("master")
        if master is None or master.blocked_at is None:
            return await handler(event, data)

        inner: TelegramObject = event.event if isinstance(event, Update) else event
        text = getattr(inner, "text", None)
        if isinstance(text, str) and text.strip() in _ALLOWED_TEXTS:
            return await handler(event, data)

        answer = getattr(inner, "answer", None)
        if callable(answer):
            await answer(strings.MASTER_BLOCKED_BANNER)
            return None
        return await handler(event, data)
