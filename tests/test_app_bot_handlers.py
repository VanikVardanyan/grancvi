from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiogram.filters import CommandObject
from aiogram.types import InlineKeyboardMarkup, WebAppInfo

from src.app_bot.handlers import handle_start


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables() -> AsyncGenerator[None, None]:
    """Override DB-truncation fixture — app_bot handler tests are stateless."""
    yield


@pytest.mark.asyncio
async def test_start_no_payload_sends_launcher() -> None:
    message = AsyncMock()
    message.from_user = MagicMock(id=42)

    await handle_start(message=message, command=CommandObject(command="start"))

    message.answer.assert_awaited_once()
    kwargs = message.answer.await_args.kwargs
    kb = kwargs.get("reply_markup")
    assert isinstance(kb, InlineKeyboardMarkup)
    button = kb.inline_keyboard[0][0]
    assert isinstance(button.web_app, WebAppInfo)
    assert button.web_app.url == "https://app.jampord.am"


@pytest.mark.asyncio
async def test_start_with_payload_forwards_start_param() -> None:
    message = AsyncMock()
    message.from_user = MagicMock(id=42)

    await handle_start(
        message=message, command=CommandObject(command="start", args="master_anna-1234")
    )

    kb = message.answer.await_args.kwargs["reply_markup"]
    button = kb.inline_keyboard[0][0]
    assert "tgWebAppStartParam=master_anna-1234" in button.web_app.url
