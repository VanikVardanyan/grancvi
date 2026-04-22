from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.handlers.admin.menu import handle_admin_start


@pytest.mark.asyncio
async def test_admin_no_master_sees_admin_menu(session: AsyncSession) -> None:
    message = AsyncMock()
    message.text = "/start"
    state = AsyncMock()

    await handle_admin_start(
        message=message,
        master=None,
        state=state,
        session=session,
        is_admin=True,
    )
    message.answer.assert_awaited()
    kwargs = message.answer.await_args.kwargs
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_admin_with_master_profile_skips_admin_start() -> None:
    from src.db.models import Master

    master = Master(tg_id=1, name="A", slug="a-0001")
    message = AsyncMock()
    state = AsyncMock()

    await handle_admin_start(
        message=message,
        master=master,
        state=state,
        session=AsyncMock(),
        is_admin=True,
    )
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_admin_noop() -> None:
    message = AsyncMock()
    state = AsyncMock()
    await handle_admin_start(
        message=message,
        master=None,
        state=state,
        session=AsyncMock(),
        is_admin=False,
    )
    message.answer.assert_not_awaited()
