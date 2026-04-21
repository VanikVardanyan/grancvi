from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.repositories.clients import ClientRepository


async def _master(session: AsyncSession, tg: int = 5100) -> Master:
    m = Master(tg_id=tg, name="M", timezone="Asia/Yerevan")
    session.add(m)
    await session.flush()
    return m


async def _service(session: AsyncSession, master: Master) -> Service:
    s = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(s)
    await session.flush()
    return s


async def _client(
    session: AsyncSession,
    master: Master,
    *,
    name: str,
    phone: str,
    created_at: datetime | None = None,
) -> Client:
    c = Client(master_id=master.id, name=name, phone=phone)
    if created_at is not None:
        c.created_at = created_at
    session.add(c)
    await session.flush()
    return c


@pytest.mark.asyncio
async def test_list_recent_empty(session: AsyncSession) -> None:
    master = await _master(session)
    await session.commit()
    repo = ClientRepository(session)
    assert await repo.list_recent_by_master(master.id) == []


@pytest.mark.asyncio
async def test_list_recent_orders_by_last_appointment(session: AsyncSession) -> None:
    master = await _master(session)
    svc = await _service(session, master)
    old = await _client(session, master, name="Old", phone="+37499000001")
    recent = await _client(session, master, name="Recent", phone="+37499000002")
    await _client(
        session,
        master,
        name="NoAppts",
        phone="+37499000003",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    session.add(
        Appointment(
            master_id=master.id,
            client_id=old.id,
            service_id=svc.id,
            start_at=datetime(2026, 3, 1, 10, tzinfo=UTC),
            end_at=datetime(2026, 3, 1, 11, tzinfo=UTC),
            status="confirmed",
            source="master_manual",
        )
    )
    session.add(
        Appointment(
            master_id=master.id,
            client_id=recent.id,
            service_id=svc.id,
            start_at=datetime(2026, 4, 15, 10, tzinfo=UTC),
            end_at=datetime(2026, 4, 15, 11, tzinfo=UTC),
            status="confirmed",
            source="master_manual",
        )
    )
    await session.commit()

    repo = ClientRepository(session)
    result = await repo.list_recent_by_master(master.id)
    assert [c.name for c in result] == ["Recent", "Old", "NoAppts"]


@pytest.mark.asyncio
async def test_list_recent_respects_master_scope(session: AsyncSession) -> None:
    m1 = await _master(session, tg=5201)
    m2 = await _master(session, tg=5202)
    await _client(session, m1, name="Mine", phone="+37499000011")
    await _client(session, m2, name="Other", phone="+37499000012")
    await session.commit()

    repo = ClientRepository(session)
    mine = await repo.list_recent_by_master(m1.id)
    assert [c.name for c in mine] == ["Mine"]


@pytest.mark.asyncio
async def test_list_recent_limit(session: AsyncSession) -> None:
    master = await _master(session)
    for i in range(12):
        await _client(session, master, name=f"C{i}", phone=f"+3749900{i:04d}")
    await session.commit()

    repo = ClientRepository(session)
    assert len(await repo.list_recent_by_master(master.id, limit=5)) == 5


@pytest.mark.asyncio
async def test_search_below_min_length_returns_empty(session: AsyncSession) -> None:
    master = await _master(session)
    await _client(session, master, name="Anna", phone="+37499111111")
    await session.commit()

    repo = ClientRepository(session)
    assert await repo.search_by_master(master.id, "a") == []


@pytest.mark.asyncio
async def test_search_by_name_substring(session: AsyncSession) -> None:
    master = await _master(session)
    await _client(session, master, name="Anna Karenina", phone="+37499000301")
    await _client(session, master, name="Bob", phone="+37499000302")
    await session.commit()

    repo = ClientRepository(session)
    assert [c.name for c in await repo.search_by_master(master.id, "ann")] == ["Anna Karenina"]


@pytest.mark.asyncio
async def test_search_by_phone_digits(session: AsyncSession) -> None:
    master = await _master(session)
    await _client(session, master, name="Anna", phone="+37499555111")
    await _client(session, master, name="Bob", phone="+37499999222")
    await session.commit()

    repo = ClientRepository(session)
    result = await repo.search_by_master(master.id, "555")
    assert [c.name for c in result] == ["Anna"]


@pytest.mark.asyncio
async def test_search_digits_in_raw_query_ignored(session: AsyncSession) -> None:
    master = await _master(session)
    await _client(session, master, name="Anna", phone="+37499555111")
    await session.commit()

    repo = ClientRepository(session)
    result = await repo.search_by_master(master.id, "5-5-5")
    assert [c.name for c in result] == ["Anna"]


@pytest.mark.asyncio
async def test_search_master_scope(session: AsyncSession) -> None:
    m1 = await _master(session, tg=5301)
    m2 = await _master(session, tg=5302)
    await _client(session, m1, name="Anna", phone="+37499000401")
    await _client(session, m2, name="Anna", phone="+37499000402")
    await session.commit()

    repo = ClientRepository(session)
    ids_m1 = {c.id for c in await repo.search_by_master(m1.id, "anna")}
    assert len(ids_m1) == 1
