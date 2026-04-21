from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.repositories.appointments import AppointmentRepository


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(tg_id=7001, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="C", phone="+37499000001")
    session.add(client)
    svc = Service(master_id=master.id, name="S", duration_min=60)
    session.add(svc)
    await session.flush()
    return master, client, svc


def _mkappt(
    *,
    master_id: object,
    client_id: object,
    service_id: object,
    start: datetime,
    status: str,
) -> Appointment:
    return Appointment(
        master_id=master_id,
        client_id=client_id,
        service_id=service_id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status=status,
        source="master_manual",
    )


@pytest.mark.asyncio
async def test_default_statuses_return_pending_and_confirmed(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    t0 = datetime(2026, 5, 1, 10, tzinfo=UTC)
    for st, hr in [
        ("pending", 10),
        ("confirmed", 11),
        ("cancelled", 12),
        ("rejected", 13),
        ("completed", 14),
        ("no_show", 15),
    ]:
        session.add(
            _mkappt(
                master_id=master.id,
                client_id=client.id,
                service_id=svc.id,
                start=t0.replace(hour=hr),
                status=st,
            )
        )
    await session.flush()

    repo = AppointmentRepository(session)
    rows = await repo.list_for_master_range(
        master.id,
        start_utc=datetime(2026, 5, 1, tzinfo=UTC),
        end_utc=datetime(2026, 5, 2, tzinfo=UTC),
    )
    statuses = sorted(r.status for r in rows)
    assert statuses == ["confirmed", "pending"]


@pytest.mark.asyncio
async def test_explicit_statuses_override_default(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    t0 = datetime(2026, 5, 1, 10, tzinfo=UTC)
    for st, hr in [("confirmed", 10), ("completed", 11), ("no_show", 12)]:
        session.add(
            _mkappt(
                master_id=master.id,
                client_id=client.id,
                service_id=svc.id,
                start=t0.replace(hour=hr),
                status=st,
            )
        )
    await session.flush()

    repo = AppointmentRepository(session)
    rows = await repo.list_for_master_range(
        master.id,
        start_utc=datetime(2026, 5, 1, tzinfo=UTC),
        end_utc=datetime(2026, 5, 2, tzinfo=UTC),
        statuses=("confirmed", "completed", "no_show"),
    )
    assert sorted(r.status for r in rows) == ["completed", "confirmed", "no_show"]


@pytest.mark.asyncio
async def test_range_is_half_open_start_inclusive_end_exclusive(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    start = datetime(2026, 5, 1, 12, tzinfo=UTC)
    session.add(
        _mkappt(
            master_id=master.id,
            client_id=client.id,
            service_id=svc.id,
            start=start,
            status="confirmed",
        )
    )
    await session.flush()

    repo = AppointmentRepository(session)
    included = await repo.list_for_master_range(
        master.id,
        start_utc=start,
        end_utc=start + timedelta(hours=1),
    )
    excluded = await repo.list_for_master_range(
        master.id,
        start_utc=start + timedelta(hours=1),
        end_utc=start + timedelta(hours=2),
    )
    assert len(included) == 1
    assert excluded == []


@pytest.mark.asyncio
async def test_other_masters_excluded(session: AsyncSession) -> None:
    master_a, client_a, svc_a = await _seed(session)
    master_b = Master(tg_id=7002, name="B", timezone="Asia/Yerevan")
    session.add(master_b)
    await session.flush()
    client_b = Client(master_id=master_b.id, name="CB", phone="+37499000099")
    svc_b = Service(master_id=master_b.id, name="SB", duration_min=60)
    session.add_all([client_b, svc_b])
    await session.flush()

    t = datetime(2026, 5, 1, 10, tzinfo=UTC)
    session.add(
        _mkappt(
            master_id=master_a.id,
            client_id=client_a.id,
            service_id=svc_a.id,
            start=t,
            status="confirmed",
        )
    )
    session.add(
        _mkappt(
            master_id=master_b.id,
            client_id=client_b.id,
            service_id=svc_b.id,
            start=t.replace(hour=11),
            status="confirmed",
        )
    )
    await session.flush()

    repo = AppointmentRepository(session)
    rows = await repo.list_for_master_range(
        master_a.id,
        start_utc=datetime(2026, 5, 1, tzinfo=UTC),
        end_utc=datetime(2026, 5, 2, tzinfo=UTC),
    )
    assert len(rows) == 1
    assert rows[0].master_id == master_a.id
