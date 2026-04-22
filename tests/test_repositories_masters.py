from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.masters import MasterRepository


@pytest.mark.asyncio
async def test_get_by_tg_id_returns_none_when_absent(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    result = await repo.get_by_tg_id(404404)
    assert result is None


@pytest.mark.asyncio
async def test_create_and_read_roundtrip(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    created = await repo.create(tg_id=111, name="Анна", phone="+37411111111")
    await session.commit()

    fetched = await repo.get_by_tg_id(111)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Анна"
    assert fetched.phone == "+37411111111"
    assert fetched.timezone == "Asia/Yerevan"


@pytest.mark.asyncio
async def test_duplicate_tg_id_raises(session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    repo = MasterRepository(session)
    await repo.create(tg_id=222, name="Борис", phone="+37422222222")
    await session.commit()

    with pytest.raises(IntegrityError):
        await repo.create(tg_id=222, name="Борис-двойник", phone="+37400000000")
        await session.commit()


@pytest.mark.asyncio
async def test_update_work_hours_persists(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    master = await repo.create(tg_id=333, name="Галина")
    await session.commit()

    await repo.update_work_hours(master.id, {"mon": [["10:00", "19:00"]]})
    await session.commit()

    fetched = await repo.get_by_tg_id(333)
    assert fetched is not None
    assert fetched.work_hours == {"mon": [["10:00", "19:00"]]}


@pytest.mark.asyncio
async def test_update_work_hours_unknown_master_is_noop(session: AsyncSession) -> None:
    from uuid import uuid4

    repo = MasterRepository(session)
    await repo.update_work_hours(uuid4(), {"mon": [["10:00", "19:00"]]})


@pytest.mark.asyncio
async def test_update_breaks_persists(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    master = await repo.create(tg_id=444, name="Давид")
    await session.commit()

    await repo.update_breaks(master.id, {"mon": [["13:00", "14:00"]]})
    await session.commit()

    fetched = await repo.get_by_tg_id(444)
    assert fetched is not None
    assert fetched.breaks == {"mon": [["13:00", "14:00"]]}


@pytest.mark.asyncio
async def test_update_breaks_unknown_master_is_noop(session: AsyncSession) -> None:
    from uuid import uuid4

    repo = MasterRepository(session)
    await repo.update_breaks(uuid4(), {"mon": [["13:00", "14:00"]]})
