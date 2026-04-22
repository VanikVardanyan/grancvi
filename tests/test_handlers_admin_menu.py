from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.handlers.admin import menu as menu_mod
from src.strings import get_bundle


@pytest.mark.asyncio
async def test_admin_masters_button_dispatches() -> None:
    message = AsyncMock()
    ru = get_bundle("ru")
    message.text = ru.ADMIN_MENU_MASTERS
    session = AsyncMock()

    with patch.object(menu_mod, "cmd_admin_masters", new=AsyncMock()) as mocked:
        await menu_mod.handle_admin_masters(message=message, session=session, is_admin=True)

    mocked.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_buttons_noop_for_non_admin() -> None:
    message = AsyncMock()
    session = AsyncMock()
    with patch.object(menu_mod, "cmd_admin_masters", new=AsyncMock()) as mocked:
        await menu_mod.handle_admin_masters(message=message, session=session, is_admin=False)
    mocked.assert_not_awaited()
