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
    master = Master(tg_id=100001, name="Анна", slug="anna-0001")
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


@pytest.mark.asyncio
async def test_master_not_shadowed_by_client_at_other_master(session: AsyncSession) -> None:
    """Regression: old code did session.scalar for client, which would crash on
    MultipleResultsFound. Even if it succeeded, we must not populate client data."""
    m1 = Master(tg_id=100001, name="A", slug="a-0001")
    m2 = Master(tg_id=100002, name="B", slug="b-0001")
    session.add_all([m1, m2])
    await session.flush()
    # Same tg_id 300001 is a client of BOTH masters
    session.add(Client(master_id=m1.id, name="X", phone="+111", tg_id=300001))
    session.add(Client(master_id=m2.id, name="X", phone="+222", tg_id=300001))
    await session.commit()

    middleware = UserMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    # Must not crash even though two clients rows exist.
    await middleware(
        handler,
        cast(TelegramObject, FakeEvent(from_user=FakeUser(id=300001))),
        {"session": session},
    )
    assert captured["master"] is None
    # Middleware no longer resolves `client` — handlers do it with master_id scope.
    assert "client" in captured  # key still present for compat
    assert captured["client"] is None


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
