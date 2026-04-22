from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.handlers.master.profile import cmd_profile_save_slug


@pytest.mark.asyncio
async def test_profile_save_slug_rejects_invalid() -> None:
    message = AsyncMock()
    message.text = "UPPER"
    state = AsyncMock()
    master = AsyncMock(id=uuid4())
    session = AsyncMock()
    await cmd_profile_save_slug(message=message, state=state, session=session, master=master)
    message.answer.assert_awaited()
    session.commit.assert_not_awaited()
