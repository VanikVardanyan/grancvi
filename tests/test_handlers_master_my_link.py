from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.handlers.master.my_link import cmd_mylink, cmd_qr


@pytest.mark.asyncio
async def test_cmd_mylink_sends_link_with_slug() -> None:
    message = AsyncMock()
    master = AsyncMock()
    master.slug = "anna-7f3c"
    with patch("src.handlers.master.my_link.strings") as mocked:
        mocked.MY_LINK_MSG_FMT = "link: {link}"
        await cmd_mylink(message=message, master=master)
    message.answer.assert_awaited_once()
    args = message.answer.await_args
    assert "anna-7f3c" in args[0][0]


@pytest.mark.asyncio
async def test_cmd_qr_sends_photo_with_link_in_caption() -> None:
    from aiogram.types import BufferedInputFile

    message = AsyncMock()
    master = AsyncMock()
    master.slug = "vanik"

    await cmd_qr(message=message, master=master)

    message.answer_photo.assert_awaited_once()
    call = message.answer_photo.await_args
    photo_arg = call.kwargs.get("photo") or (call.args[0] if call.args else None)
    assert isinstance(photo_arg, BufferedInputFile)
    caption = call.kwargs.get("caption", "")
    assert "vanik" in caption
    assert "t.me/" in caption
