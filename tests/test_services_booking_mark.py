from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.exceptions import InvalidState, NotFound
from src.services.booking import BookingService


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(tg_id=7201, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="C", phone="+37499001001")
    svc = Service(master_id=master.id, name="S", duration_min=60)
    session.add_all([client, svc])
    await session.flush()
    return master, client, svc


def _mk_confirmed(*, master: Master, client: Client, svc: Service, start: datetime) -> Appointment:
    return Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=svc.id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status="confirmed",
        source="master_manual",
        confirmed_at=start - timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_mark_completed_promotes_past_confirmed(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    now = datetime(2026, 5, 2, 12, tzinfo=UTC)
    appt = _mk_confirmed(master=master, client=client, svc=svc, start=now - timedelta(hours=3))
    session.add(appt)
    await session.flush()

    svc_b = BookingService(session)
    updated = await svc_b.mark_completed(appt.id, master=master, now=now)
    assert updated.status == "completed"


@pytest.mark.asyncio
async def test_mark_no_show_promotes_past_confirmed(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    now = datetime(2026, 5, 2, 12, tzinfo=UTC)
    appt = _mk_confirmed(master=master, client=client, svc=svc, start=now - timedelta(hours=3))
    session.add(appt)
    await session.flush()

    svc_b = BookingService(session)
    updated = await svc_b.mark_no_show(appt.id, master=master, now=now)
    assert updated.status == "no_show"


@pytest.mark.asyncio
async def test_mark_completed_refuses_future_end(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    now = datetime(2026, 5, 2, 12, tzinfo=UTC)
    # starts now, ends in +60 min → end_at > now
    appt = _mk_confirmed(master=master, client=client, svc=svc, start=now)
    session.add(appt)
    await session.flush()

    svc_b = BookingService(session)
    with pytest.raises(InvalidState):
        await svc_b.mark_completed(appt.id, master=master, now=now)


@pytest.mark.asyncio
async def test_mark_completed_refuses_non_confirmed(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    now = datetime(2026, 5, 2, 12, tzinfo=UTC)
    appt = _mk_confirmed(master=master, client=client, svc=svc, start=now - timedelta(hours=3))
    appt.status = "completed"
    session.add(appt)
    await session.flush()

    svc_b = BookingService(session)
    with pytest.raises(InvalidState):
        await svc_b.mark_completed(appt.id, master=master, now=now)


@pytest.mark.asyncio
async def test_mark_completed_wrong_master_is_not_found(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    other = Master(tg_id=7202, name="O", timezone="Asia/Yerevan")
    session.add(other)
    await session.flush()
    now = datetime(2026, 5, 2, 12, tzinfo=UTC)
    appt = _mk_confirmed(master=master, client=client, svc=svc, start=now - timedelta(hours=3))
    session.add(appt)
    await session.flush()

    svc_b = BookingService(session)
    with pytest.raises(NotFound):
        await svc_b.mark_completed(appt.id, master=other, now=now)


@pytest.mark.asyncio
async def test_mark_no_show_missing_id(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    svc_b = BookingService(session)
    with pytest.raises(NotFound):
        await svc_b.mark_no_show(uuid4(), master=master, now=datetime.now(UTC))
