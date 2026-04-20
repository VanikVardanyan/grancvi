from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.db.models import Master
from src.strings import DEFAULT_LANG, SUPPORTED_LANGS, set_current_lang


class LangMiddleware(BaseMiddleware):
    """Resolve the request language from master.lang / Telegram language_code.

    Order of precedence:
      1. `data["master"].lang` (registered master) — highest.
      2. `event.from_user.language_code` if it's in SUPPORTED_LANGS.
      3. DEFAULT_LANG.

    Must run AFTER UserMiddleware (which populates `data["master"]`).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        lang = self._resolve(event, data)
        set_current_lang(lang)
        data["lang"] = lang
        return await handler(event, data)

    @staticmethod
    def _resolve(event: TelegramObject, data: dict[str, Any]) -> str:
        master = data.get("master")
        if isinstance(master, Master) and master.lang in SUPPORTED_LANGS:
            return master.lang
        inner = event.event if isinstance(event, Update) else event
        tg_user = getattr(inner, "from_user", None)
        code = getattr(tg_user, "language_code", None)
        if isinstance(code, str) and code in SUPPORTED_LANGS:
            return code
        return DEFAULT_LANG
