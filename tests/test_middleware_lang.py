from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.types import Chat, Message, Update, User

from src.db.models import Master
from src.middlewares.lang import LangMiddleware
from src.strings import DEFAULT_LANG, get_current_lang, set_current_lang


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables() -> AsyncGenerator[None, None]:
    """Override DB-truncation fixture — these are pure unit tests, no DB needed."""
    yield


class _FakeStorage:
    def __init__(self, data: dict[StorageKey, dict[str, Any]] | None = None) -> None:
        self._data: dict[StorageKey, dict[str, Any]] = data or {}

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        return dict(self._data.get(key, {}))


def _make_update(*, user_id: int, chat_id: int, language_code: str | None = None) -> Update:
    user = User(id=user_id, is_bot=False, first_name="U", language_code=language_code)
    chat = Chat(id=chat_id, type="private")
    message = Message.model_construct(
        message_id=1,
        date=0,  # type: ignore[arg-type]
        chat=chat,
        from_user=user,
        text="/foo",
    )
    return Update.model_construct(update_id=1, message=message)


async def _run_middleware(
    *,
    storage: BaseStorage,
    master: Master | None,
    update: Update,
) -> str:
    mw = LangMiddleware(storage)  # type: ignore[arg-type]
    bot = MagicMock()
    bot.id = 777
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured["lang"] = get_current_lang()
        captured["data_lang"] = data.get("lang")

    data = {"master": master, "bot": bot}
    await mw(handler, update, data)
    return captured["lang"]


@pytest.mark.asyncio
async def test_lang_middleware_prefers_master_lang_over_state() -> None:
    set_current_lang(DEFAULT_LANG)
    key = StorageKey(bot_id=777, chat_id=42, user_id=42)
    storage = _FakeStorage({key: {"lang": "hy"}})
    master = Master(tg_id=42, name="M", lang="ru", timezone="Asia/Yerevan")

    lang = await _run_middleware(
        storage=storage,  # type: ignore[arg-type]
        master=master,
        update=_make_update(user_id=42, chat_id=42),
    )

    assert lang == "ru"


@pytest.mark.asyncio
async def test_lang_middleware_reads_fsm_state_when_no_master() -> None:
    set_current_lang(DEFAULT_LANG)
    key = StorageKey(bot_id=777, chat_id=42, user_id=42)
    storage = _FakeStorage({key: {"lang": "hy"}})

    lang = await _run_middleware(
        storage=storage,  # type: ignore[arg-type]
        master=None,
        update=_make_update(user_id=42, chat_id=42, language_code="ru"),
    )

    assert lang == "hy"


@pytest.mark.asyncio
async def test_lang_middleware_falls_back_to_telegram_language_code() -> None:
    set_current_lang(DEFAULT_LANG)
    storage = _FakeStorage()

    lang = await _run_middleware(
        storage=storage,  # type: ignore[arg-type]
        master=None,
        update=_make_update(user_id=42, chat_id=42, language_code="hy"),
    )

    assert lang == "hy"


@pytest.mark.asyncio
async def test_lang_middleware_default_when_nothing_resolves() -> None:
    set_current_lang("hy")
    storage = _FakeStorage()

    lang = await _run_middleware(
        storage=storage,  # type: ignore[arg-type]
        master=None,
        update=_make_update(user_id=42, chat_id=42, language_code="en"),
    )

    assert lang == DEFAULT_LANG


@pytest.mark.asyncio
async def test_lang_middleware_handles_storage_errors_gracefully() -> None:
    set_current_lang(DEFAULT_LANG)
    storage = AsyncMock()
    storage.get_data.side_effect = RuntimeError("redis down")

    lang = await _run_middleware(
        storage=storage,
        master=None,
        update=_make_update(user_id=42, chat_id=42, language_code="hy"),
    )

    assert lang == "hy"
