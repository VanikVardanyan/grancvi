from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.db.models import Master
from src.handlers.admin.menu import IsAdminNoMaster, handle_admin_start


@pytest.mark.asyncio
async def test_admin_no_master_sees_admin_menu() -> None:
    message = AsyncMock()
    message.text = "/start"
    state = AsyncMock()

    await handle_admin_start(message=message, state=state)
    message.answer.assert_awaited()
    kwargs = message.answer.await_args.kwargs
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_filter_gates_admin_without_master() -> None:
    f = IsAdminNoMaster()
    msg = AsyncMock()
    msg.text = "/start"
    assert await f(msg, is_admin=True, master=None) is True


@pytest.mark.asyncio
async def test_filter_rejects_admin_with_master() -> None:
    f = IsAdminNoMaster()
    master = Master(tg_id=1, name="A", slug="a-0001")
    msg = AsyncMock()
    msg.text = "/start"
    assert await f(msg, is_admin=True, master=master) is False


@pytest.mark.asyncio
async def test_filter_rejects_non_admin() -> None:
    f = IsAdminNoMaster()
    msg = AsyncMock()
    msg.text = "/start"
    assert await f(msg, is_admin=False, master=None) is False


@pytest.mark.asyncio
async def test_filter_rejects_admin_with_master_deep_link() -> None:
    """Admin scanning another master's QR/link should fall through to client
    booking, not hit the admin menu."""
    f = IsAdminNoMaster()
    msg = AsyncMock()
    msg.text = "/start master_anna-0001"
    assert await f(msg, is_admin=True, master=None) is False
