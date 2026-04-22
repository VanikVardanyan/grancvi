from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from unittest.mock import AsyncMock

import pytest
from aiogram.types import TelegramObject

from src.db.models import Master
from src.middlewares.blocked_guard import BlockedMasterGuardMiddleware
from src.utils.time import now_utc


@dataclass
class FakeMessage:
    text: str
    answer: AsyncMock


@pytest.mark.asyncio
async def test_blocked_master_gets_banner_on_menu_button() -> None:
    master = Master(
        tg_id=1,
        name="A",
        slug="a-0001",
        blocked_at=now_utc(),
    )
    middleware = BlockedMasterGuardMiddleware()
    msg = FakeMessage(text="📅 Сегодня", answer=AsyncMock())
    handler = AsyncMock()

    await middleware(handler, cast(TelegramObject, msg), {"master": master})
    handler.assert_not_awaited()
    msg.answer.assert_awaited_once()
    from src.strings import get_bundle

    ru = get_bundle("ru")
    assert ru.MASTER_BLOCKED_BANNER in msg.answer.await_args[0][0]


@pytest.mark.asyncio
async def test_start_passes_through_when_blocked() -> None:
    master = Master(
        tg_id=1,
        name="A",
        slug="a-0001",
        blocked_at=now_utc(),
    )
    middleware = BlockedMasterGuardMiddleware()
    msg = FakeMessage(text="/start", answer=AsyncMock())
    handler = AsyncMock()

    await middleware(handler, cast(TelegramObject, msg), {"master": master})
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_master_passes_through() -> None:
    master = Master(tg_id=1, name="A", slug="a-0001")
    middleware = BlockedMasterGuardMiddleware()
    msg = FakeMessage(text="📅 Сегодня", answer=AsyncMock())
    handler = AsyncMock()

    await middleware(handler, cast(TelegramObject, msg), {"master": master})
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_master_passes_through() -> None:
    middleware = BlockedMasterGuardMiddleware()
    msg = FakeMessage(text="📅 Сегодня", answer=AsyncMock())
    handler = AsyncMock()

    await middleware(handler, cast(TelegramObject, msg), {"master": None})
    handler.assert_awaited_once()
