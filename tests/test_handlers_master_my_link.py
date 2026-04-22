from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.handlers.master.my_link import cmd_mylink


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
