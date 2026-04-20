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
