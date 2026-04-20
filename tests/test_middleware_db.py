from __future__ import annotations

from typing import Any, cast

import pytest
from aiogram.types import TelegramObject
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.middlewares.db import DbSessionMiddleware


@pytest.mark.asyncio
async def test_middleware_injects_session_and_commits(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    middleware = DbSessionMiddleware(session_maker)
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured["session"] = data["session"]
        await data["session"].execute(text("SELECT 1"))

    await middleware(handler, event=cast(TelegramObject, object()), data={})
    assert isinstance(captured["session"], AsyncSession)


@pytest.mark.asyncio
async def test_middleware_rolls_back_on_exception(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    middleware = DbSessionMiddleware(session_maker)

    async def handler(event: Any, data: dict[str, Any]) -> None:
        await data["session"].execute(text("SELECT 1"))
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await middleware(handler, event=cast(TelegramObject, object()), data={})
