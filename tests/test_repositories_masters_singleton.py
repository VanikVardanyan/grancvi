from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.masters import MasterRepository


@pytest.mark.asyncio
async def test_get_singleton_empty(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    assert await repo.get_singleton() is None


@pytest.mark.asyncio
async def test_get_singleton_returns_only_master(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    created = await repo.create(tg_id=777, name="Единственный")
    await session.commit()

    fetched = await repo.get_singleton()
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_singleton_returns_first_when_multiple(session: AsyncSession) -> None:
    """v0.1 invariant is one master, but be deterministic if it's ever violated."""
    repo = MasterRepository(session)
    a = await repo.create(tg_id=1001, name="Первый")
    await session.commit()
    _ = await repo.create(tg_id=1002, name="Второй")
    await session.commit()

    fetched = await repo.get_singleton()
    assert fetched is not None
    assert fetched.id == a.id  # ORDER BY created_at ASC LIMIT 1
