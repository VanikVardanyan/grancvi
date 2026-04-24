from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from src.utils.client_notify import notify_client


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables() -> AsyncGenerator[None, None]:
    """Override DB-truncation fixture — pure unit tests, no DB needed."""
    yield


def _make_forbidden() -> TelegramForbiddenError:
    return TelegramForbiddenError(method=None, message="bot was blocked by the user")  # type: ignore[arg-type]


def _make_bad_request() -> TelegramBadRequest:
    return TelegramBadRequest(method=None, message="chat not found")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_sends_via_app_bot_when_available() -> None:
    app_bot = AsyncMock()
    master_bot = AsyncMock()
    ok = await notify_client(app_bot=app_bot, fallback_bot=master_bot, chat_id=123, text="hi")
    assert ok is True
    app_bot.send_message.assert_awaited_once_with(chat_id=123, text="hi", reply_markup=None)
    master_bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_forbidden_on_app_bot_falls_back_to_master_bot() -> None:
    app_bot = AsyncMock()
    app_bot.send_message.side_effect = _make_forbidden()
    master_bot = AsyncMock()
    ok = await notify_client(app_bot=app_bot, fallback_bot=master_bot, chat_id=123, text="hi")
    assert ok is True
    master_bot.send_message.assert_awaited_once_with(chat_id=123, text="hi", reply_markup=None)


@pytest.mark.asyncio
async def test_bad_request_on_app_bot_also_falls_back() -> None:
    app_bot = AsyncMock()
    app_bot.send_message.side_effect = _make_bad_request()
    master_bot = AsyncMock()
    ok = await notify_client(app_bot=app_bot, fallback_bot=master_bot, chat_id=123, text="hi")
    assert ok is True
    master_bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_app_bot_uses_master_bot_directly() -> None:
    master_bot = AsyncMock()
    ok = await notify_client(app_bot=None, fallback_bot=master_bot, chat_id=123, text="hi")
    assert ok is True
    master_bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_both_fail_returns_false() -> None:
    app_bot = AsyncMock()
    app_bot.send_message.side_effect = _make_forbidden()
    master_bot = AsyncMock()
    master_bot.send_message.side_effect = _make_forbidden()
    ok = await notify_client(app_bot=app_bot, fallback_bot=master_bot, chat_id=123, text="hi")
    assert ok is False


@pytest.mark.asyncio
async def test_reply_markup_passed_through() -> None:
    app_bot = AsyncMock()
    master_bot = AsyncMock()
    kb = object()
    await notify_client(
        app_bot=app_bot, fallback_bot=master_bot, chat_id=1, text="x", reply_markup=kb
    )
    app_bot.send_message.assert_awaited_once_with(chat_id=1, text="x", reply_markup=kb)
