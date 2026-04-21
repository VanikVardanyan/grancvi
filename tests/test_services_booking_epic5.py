from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.exceptions import InvalidState, NotFound
from src.services.booking import BookingService


async def _seed(
    session: AsyncSession, *, client_tg: int | None = 7001
) -> tuple[Master, Client, Service, Appointment]:
    master = Master(tg_id=6101, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499111111", tg_id=client_tg)
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="confirmed",
        source="client_request",
    )
    session.add(appt)
    await session.flush()
    return master, client, service, appt


@pytest.mark.asyncio
async def test_cancel_by_client_happy_path(session: AsyncSession) -> None:
    master, client, service, appt = await _seed(session)
    await session.commit()

    svc = BookingService(session)
    out_appt, out_client, out_master, out_service = await svc.cancel_by_client(appt.id, tg_id=7001)
    assert out_appt.status == "cancelled"
    assert out_appt.cancelled_by == "client"
    assert out_appt.cancelled_at is not None
    assert out_client.id == client.id
    assert out_master.id == master.id
    assert out_service.id == service.id


@pytest.mark.asyncio
async def test_cancel_by_client_wrong_tg_id_raises_notfound(session: AsyncSession) -> None:
    _m, _c, _s, appt = await _seed(session)
    await session.commit()

    with pytest.raises(NotFound):
        await BookingService(session).cancel_by_client(appt.id, tg_id=9999)


@pytest.mark.asyncio
async def test_cancel_by_client_no_tg_id_on_client_raises_notfound(session: AsyncSession) -> None:
    _m, _c, _s, appt = await _seed(session, client_tg=None)
    await session.commit()

    with pytest.raises(NotFound):
        await BookingService(session).cancel_by_client(appt.id, tg_id=7001)


@pytest.mark.asyncio
async def test_cancel_by_client_missing_appointment_raises_notfound(session: AsyncSession) -> None:
    svc = BookingService(session)
    with pytest.raises(NotFound):
        await svc.cancel_by_client(uuid4(), tg_id=7001)


@pytest.mark.asyncio
async def test_cancel_by_client_already_cancelled_raises_invalid_state(
    session: AsyncSession,
) -> None:
    _m, _c, _s, appt = await _seed(session)
    appt.status = "cancelled"
    appt.cancelled_at = datetime(2026, 5, 1, tzinfo=UTC)
    appt.cancelled_by = "client"
    await session.commit()

    with pytest.raises(InvalidState):
        await BookingService(session).cancel_by_client(appt.id, tg_id=7001)
