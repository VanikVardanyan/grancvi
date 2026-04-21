from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.repositories.clients import ClientRepository


async def _seed_master(session: AsyncSession, tg_id: int = 5001) -> Master:
    master = Master(tg_id=tg_id, name="Мастер")
    session.add(master)
    await session.flush()
    return master


@pytest.mark.asyncio
async def test_get_returns_none_when_absent(session: AsyncSession) -> None:
    repo = ClientRepository(session)
    assert await repo.get(uuid4()) is None


@pytest.mark.asyncio
async def test_upsert_inserts_new_client(session: AsyncSession) -> None:
    master = await _seed_master(session)
    await session.commit()

    repo = ClientRepository(session)
    client = await repo.upsert_by_phone(
        master_id=master.id, phone="+37499111222", name="Аня", tg_id=42
    )
    await session.commit()

    assert client.id is not None
    assert client.name == "Аня"
    assert client.phone == "+37499111222"
    assert client.tg_id == 42
    assert client.master_id == master.id


@pytest.mark.asyncio
async def test_upsert_updates_name_and_tg_id(session: AsyncSession) -> None:
    master = await _seed_master(session)
    await session.commit()

    repo = ClientRepository(session)
    first = await repo.upsert_by_phone(
        master_id=master.id, phone="+37499111222", name="Старое имя", tg_id=None
    )
    await session.commit()

    second = await repo.upsert_by_phone(
        master_id=master.id, phone="+37499111222", name="Новое имя", tg_id=99
    )
    await session.commit()

    assert second.id == first.id
    assert second.name == "Новое имя"
    assert second.tg_id == 99


@pytest.mark.asyncio
async def test_upsert_scoped_by_master(session: AsyncSession) -> None:
    master_a = await _seed_master(session, tg_id=7001)
    master_b = await _seed_master(session, tg_id=7002)
    await session.commit()

    repo = ClientRepository(session)
    a = await repo.upsert_by_phone(
        master_id=master_a.id, phone="+37499000000", name="A", tg_id=None
    )
    b = await repo.upsert_by_phone(
        master_id=master_b.id, phone="+37499000000", name="B", tg_id=None
    )
    await session.commit()

    assert a.id != b.id
    assert a.master_id == master_a.id
    assert b.master_id == master_b.id


@pytest.mark.asyncio
async def test_upsert_does_not_overwrite_tg_id_with_none(session: AsyncSession) -> None:
    master = await _seed_master(session)
    await session.commit()

    repo = ClientRepository(session)
    await repo.upsert_by_phone(
        master_id=master.id,
        phone="+37499111222",
        name="Х",
        tg_id=555,  # noqa: RUF001
    )
    await session.commit()

    updated = await repo.upsert_by_phone(
        master_id=master.id,
        phone="+37499111222",
        name="Х",
        tg_id=None,  # noqa: RUF001
    )
    await session.commit()

    assert updated.tg_id == 555
