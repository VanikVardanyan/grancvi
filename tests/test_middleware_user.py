from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master
from src.middlewares.user import UserMiddleware


@dataclass
class FakeUser:
    id: int


@dataclass
class FakeEvent:
    from_user: FakeUser


@pytest.mark.asyncio
async def test_resolves_existing_master(session: AsyncSession) -> None:
    master = Master(tg_id=100001, name="Анна")
    session.add(master)
    await session.commit()

    middleware = UserMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    await middleware(
        handler,
        cast(TelegramObject, FakeEvent(from_user=FakeUser(id=100001))),
        {"session": session},
    )

    assert captured["master"] is not None
    assert captured["master"].tg_id == 100001
    assert captured["client"] is None


@pytest.mark.asyncio
async def test_resolves_existing_client(session: AsyncSession) -> None:
    master = Master(tg_id=200001, name="Борис")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Вера", phone="+37499000001", tg_id=300001)  # noqa: RUF001
    session.add(client)
    await session.commit()

    middleware = UserMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    await middleware(
        handler,
        cast(TelegramObject, FakeEvent(from_user=FakeUser(id=300001))),
        {"session": session},
    )

    assert captured["master"] is None
    assert captured["client"] is not None
    assert captured["client"].tg_id == 300001


@pytest.mark.asyncio
async def test_unknown_user_has_nones(session: AsyncSession) -> None:
    middleware = UserMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    await middleware(
        handler,
        cast(TelegramObject, FakeEvent(from_user=FakeUser(id=999999))),
        {"session": session},
    )

    assert captured["master"] is None
    assert captured["client"] is None
