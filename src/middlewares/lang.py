from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from src.db.models import Master
from src.strings import DEFAULT_LANG, SUPPORTED_LANGS, set_current_lang

log: structlog.stdlib.BoundLogger = structlog.get_logger()


class LangMiddleware(BaseMiddleware):
    """Resolve the request language.

    Order of precedence:
      1. `data["master"].lang` (registered master) — highest.
      2. `lang` stored in FSM state (mid-registration user).
      3. `event.from_user.language_code` if it's in SUPPORTED_LANGS.
      4. DEFAULT_LANG.

    Must run AFTER UserMiddleware (which populates `data["master"]`).
    Needs access to the Dispatcher's FSM storage to resolve the current
    state data — `dp.update.middleware` runs before aiogram builds the
    per-handler FSMContext, so we read the storage directly.
    """

    def __init__(self, storage: BaseStorage) -> None:
        self._storage = storage

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        lang = await self._resolve(event, data)
        set_current_lang(lang)
        data["lang"] = lang
        return await handler(event, data)

    async def _resolve(self, event: TelegramObject, data: dict[str, Any]) -> str:
        master = data.get("master")
        if isinstance(master, Master) and master.lang in SUPPORTED_LANGS:
            return master.lang

        inner = event.event if isinstance(event, Update) else event
        tg_user = getattr(inner, "from_user", None)

        chat_id = self._extract_chat_id(inner)
        bot = data.get("bot")
        bot_id = getattr(bot, "id", None)

        if tg_user is not None and chat_id is not None and bot_id is not None:
            key = StorageKey(bot_id=bot_id, chat_id=chat_id, user_id=tg_user.id)
            try:
                fsm_data = await self._storage.get_data(key=key)
            except Exception:
                log.warning("lang_middleware_storage_failed", exc_info=True)
                fsm_data = {}
            state_lang = fsm_data.get("lang") if isinstance(fsm_data, dict) else None
            if isinstance(state_lang, str) and state_lang in SUPPORTED_LANGS:
                return state_lang

        code = getattr(tg_user, "language_code", None)
        if isinstance(code, str) and code in SUPPORTED_LANGS:
            return code
        return DEFAULT_LANG

    @staticmethod
    def _extract_chat_id(inner: Any) -> int | None:
        if isinstance(inner, Message):
            return inner.chat.id
        if isinstance(inner, CallbackQuery) and isinstance(inner.message, Message):
            return inner.message.chat.id
        chat = getattr(inner, "chat", None)
        return getattr(chat, "id", None)
