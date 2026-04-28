from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from aiogram.filters import CommandObject
from aiogram.types import InlineKeyboardMarkup, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession

from src.app_bot.handlers import handle_start


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables() -> AsyncGenerator[None, None]:
    """Override DB-truncation fixture — app_bot handler tests are stateless."""
    yield


@pytest.mark.asyncio
async def test_start_no_payload_sends_launcher() -> None:
    message = AsyncMock()
    message.from_user = MagicMock(id=42, language_code="ru")
    message.chat = MagicMock(id=42)
    bot = AsyncMock()
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None

    await handle_start(
        message=message,
        bot=bot,
        session=session,
        command=CommandObject(command="start"),
    )

    message.answer.assert_awaited_once()
    kwargs = message.answer.await_args.kwargs
    kb = kwargs.get("reply_markup")
    assert isinstance(kb, InlineKeyboardMarkup)
    button = kb.inline_keyboard[0][0]
    assert isinstance(button.web_app, WebAppInfo)
    assert button.web_app.url == "https://app.grancvi.am"


@pytest.mark.asyncio
async def test_start_with_payload_forwards_start_param() -> None:
    message = AsyncMock()
    message.from_user = MagicMock(id=42, language_code="ru")
    message.chat = MagicMock(id=42)
    bot = AsyncMock()
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None

    await handle_start(
        message=message,
        bot=bot,
        session=session,
        command=CommandObject(command="start", args="master_anna-1234"),
    )

    kb = message.answer.await_args.kwargs["reply_markup"]
    button = kb.inline_keyboard[0][0]
    assert "tgWebAppStartParam=master_anna-1234" in button.web_app.url


def test_inline_label_signup_armenian() -> None:
    from src.app_bot.handlers import _inline_label_for

    assert _inline_label_for("signup", "hy") == "Դառնալ վարպետ"


def test_inline_label_signup_russian() -> None:
    from src.app_bot.handlers import _inline_label_for

    assert _inline_label_for("signup", "ru") == "Стать мастером"


def test_inline_label_signup_salon_armenian() -> None:
    from src.app_bot.handlers import _inline_label_for

    assert _inline_label_for("signup-salon", "hy") == "Գրանցել սրահ"


def test_inline_label_signup_salon_russian() -> None:
    from src.app_bot.handlers import _inline_label_for

    assert _inline_label_for("signup-salon", "ru") == "Зарегистрировать салон"


def test_inline_label_master_link_keeps_booking_copy() -> None:
    from src.app_bot.handlers import _inline_label_for

    assert _inline_label_for("master_anna-1234", "hy") == "Գրանցվել"
    assert _inline_label_for("master_anna-1234", "ru") == "Записаться"


def test_inline_label_invite() -> None:
    from src.app_bot.handlers import _inline_label_for

    assert _inline_label_for("invite_abc123", "hy") == "Ընդունել հրավերը"
    assert _inline_label_for("invite_abc123", "ru") == "Принять приглашение"


def test_inline_label_no_param() -> None:
    from src.app_bot.handlers import _inline_label_for

    assert _inline_label_for(None, "hy") == "Բացել"
    assert _inline_label_for(None, "ru") == "Открыть"


def test_resolve_lang_default_is_armenian() -> None:
    from src.app_bot.handlers import _resolve_lang_default

    assert _resolve_lang_default(saved_lang=None) == "hy"


def test_resolve_lang_default_respects_saved_lang() -> None:
    from src.app_bot.handlers import _resolve_lang_default

    assert _resolve_lang_default(saved_lang="ru") == "ru"
    assert _resolve_lang_default(saved_lang="en") == "en"
    assert _resolve_lang_default(saved_lang="hy") == "hy"


def test_resolve_lang_default_ignores_unknown_lang() -> None:
    from src.app_bot.handlers import _resolve_lang_default

    assert _resolve_lang_default(saved_lang="zz") == "hy"
    assert _resolve_lang_default(saved_lang="") == "hy"
