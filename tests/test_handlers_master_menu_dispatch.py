from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.handlers.master import menu as menu_mod


@pytest.mark.asyncio
async def test_tomorrow_button_dispatches_to_cmd_tomorrow() -> None:
    message = AsyncMock()
    state = AsyncMock()
    session = AsyncMock()
    master = AsyncMock(id=uuid4())

    with patch.object(menu_mod, "cmd_tomorrow", new=AsyncMock()) as mocked:
        await menu_mod.handle_tomorrow(message=message, state=state, session=session, master=master)

    mocked.assert_awaited_once_with(message=message, state=state, session=session, master=master)


@pytest.mark.asyncio
async def test_week_button_dispatches_to_cmd_week() -> None:
    message = AsyncMock()
    state = AsyncMock()
    session = AsyncMock()
    master = AsyncMock(id=uuid4())

    with patch.object(menu_mod, "cmd_week", new=AsyncMock()) as mocked:
        await menu_mod.handle_week(message=message, state=state, session=session, master=master)

    mocked.assert_awaited_once_with(message=message, state=state, session=session, master=master)


@pytest.mark.asyncio
async def test_client_button_dispatches_to_cmd_client() -> None:
    message = AsyncMock()
    state = AsyncMock()
    session = AsyncMock()
    master = AsyncMock(id=uuid4())

    with patch.object(menu_mod, "cmd_client", new=AsyncMock()) as mocked:
        await menu_mod.handle_client(message=message, state=state, session=session, master=master)

    mocked.assert_awaited_once_with(message=message, state=state, session=session, master=master)


@pytest.mark.asyncio
async def test_my_link_button_dispatches_to_cmd_mylink() -> None:
    message = AsyncMock()
    master = AsyncMock(id=uuid4())

    with patch.object(menu_mod, "cmd_mylink", new=AsyncMock()) as mocked:
        await menu_mod.handle_my_link(message=message, master=master)

    mocked.assert_awaited_once_with(message=message, master=master)


@pytest.mark.asyncio
async def test_my_link_noop_for_non_master() -> None:
    message = AsyncMock()
    with patch.object(menu_mod, "cmd_mylink", new=AsyncMock()) as mocked:
        await menu_mod.handle_my_link(message=message, master=None)
    mocked.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_buttons_noop_for_non_master() -> None:
    message = AsyncMock()
    state = AsyncMock()
    session = AsyncMock()

    with (
        patch.object(menu_mod, "cmd_tomorrow", new=AsyncMock()) as m_tomorrow,
        patch.object(menu_mod, "cmd_week", new=AsyncMock()) as m_week,
        patch.object(menu_mod, "cmd_client", new=AsyncMock()) as m_client,
    ):
        await menu_mod.handle_tomorrow(message=message, state=state, session=session, master=None)
        await menu_mod.handle_week(message=message, state=state, session=session, master=None)
        await menu_mod.handle_client(message=message, state=state, session=session, master=None)

    m_tomorrow.assert_not_awaited()
    m_week.assert_not_awaited()
    m_client.assert_not_awaited()
