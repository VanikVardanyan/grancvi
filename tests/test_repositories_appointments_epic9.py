from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.repositories.appointments import AppointmentRepository


@pytest.mark.asyncio
async def test_bulk_reject_pending_only(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="a-0001")
    session.add(m)
    await session.flush()
    svc = Service(master_id=m.id, name="cut", duration_min=30)
    session.add(svc)
    cli = Client(master_id=m.id, name="C", phone="+37499000001")
    session.add(cli)
    await session.flush()

    now = datetime.now(timezone.utc)
    pending = Appointment(
        master_id=m.id, client_id=cli.id, service_id=svc.id,
        start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=2),
        status="pending", source="client_request",
    )
    confirmed = Appointment(
        master_id=m.id, client_id=cli.id, service_id=svc.id,
        start_at=now + timedelta(hours=3), end_at=now + timedelta(hours=4),
        status="confirmed", source="client_request",
    )
    session.add_all([pending, confirmed])
    await session.commit()

    repo = AppointmentRepository(session)
    affected = await repo.bulk_reject_pending_for_master(m.id, reason="master_blocked")
    await session.commit()

    await session.refresh(pending)
    await session.refresh(confirmed)
    assert pending.status == "rejected"
    assert confirmed.status == "confirmed"
    assert len(affected) == 1
    assert affected[0].id == pending.id


@pytest.mark.asyncio
async def test_bulk_reject_other_master_untouched(session: AsyncSession) -> None:
    m1 = Master(tg_id=1, name="A", slug="a-0001")
    m2 = Master(tg_id=2, name="B", slug="b-0001")
    session.add_all([m1, m2])
    await session.flush()
    svc1 = Service(master_id=m1.id, name="cut", duration_min=30)
    svc2 = Service(master_id=m2.id, name="cut", duration_min=30)
    cli1 = Client(master_id=m1.id, name="C1", phone="+111")
    cli2 = Client(master_id=m2.id, name="C2", phone="+222")
    session.add_all([svc1, svc2, cli1, cli2])
    await session.flush()

    now = datetime.now(timezone.utc)
    a1 = Appointment(
        master_id=m1.id, client_id=cli1.id, service_id=svc1.id,
        start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=2),
        status="pending", source="client_request",
    )
    a2 = Appointment(
        master_id=m2.id, client_id=cli2.id, service_id=svc2.id,
        start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=2),
        status="pending", source="client_request",
    )
    session.add_all([a1, a2])
    await session.commit()

    repo = AppointmentRepository(session)
    await repo.bulk_reject_pending_for_master(m1.id, reason="master_blocked")
    await session.commit()

    await session.refresh(a1)
    await session.refresh(a2)
    assert a1.status == "rejected"
    assert a2.status == "pending"
