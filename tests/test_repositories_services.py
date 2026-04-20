from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.repositories.services import ServiceRepository


async def _make_master(session: AsyncSession, tg_id: int = 555) -> Master:
    master = Master(tg_id=tg_id, name="Мастер")
    session.add(master)
    await session.flush()
    return master


@pytest.mark.asyncio
async def test_list_active_empty(session: AsyncSession) -> None:
    master = await _make_master(session)
    repo = ServiceRepository(session)
    result = await repo.list_active(master.id)
    assert result == []


@pytest.mark.asyncio
async def test_create_and_list(session: AsyncSession) -> None:
    master = await _make_master(session)
    repo = ServiceRepository(session)

    a = await repo.create(master_id=master.id, name="Чистка", duration_min=45)
    b = await repo.create(master_id=master.id, name="Пломба", duration_min=30)
    await session.commit()

    result = await repo.list_active(master.id)
    assert {s.id for s in result} == {a.id, b.id}
    assert all(s.active for s in result)


@pytest.mark.asyncio
async def test_update_name_and_duration(session: AsyncSession) -> None:
    master = await _make_master(session)
    repo = ServiceRepository(session)
    s = await repo.create(master_id=master.id, name="Old", duration_min=20)
    await session.commit()

    await repo.update(s.id, master_id=master.id, name="New", duration_min=35)
    await session.commit()

    refreshed = await repo.get(s.id, master_id=master.id)
    assert refreshed is not None
    assert refreshed.name == "New"
    assert refreshed.duration_min == 35


@pytest.mark.asyncio
async def test_toggle_active_hides_from_list(session: AsyncSession) -> None:
    master = await _make_master(session)
    repo = ServiceRepository(session)
    s = await repo.create(master_id=master.id, name="Тест", duration_min=20)
    await session.commit()

    await repo.set_active(s.id, master_id=master.id, active=False)
    await session.commit()

    assert await repo.list_active(master.id) == []
    # but get() by id still finds it — deletion is soft
    assert await repo.get(s.id, master_id=master.id) is not None


@pytest.mark.asyncio
async def test_update_other_masters_service_is_noop(session: AsyncSession) -> None:
    alice = await _make_master(session, tg_id=1)
    bob = await _make_master(session, tg_id=2)
    repo = ServiceRepository(session)

    s = await repo.create(master_id=alice.id, name="Alice's", duration_min=20)
    await session.commit()

    result = await repo.update(s.id, master_id=bob.id, name="Hijacked", duration_min=99)
    assert result is None
    refreshed = await repo.get(s.id, master_id=alice.id)
    assert refreshed is not None
    assert refreshed.name == "Alice's"
