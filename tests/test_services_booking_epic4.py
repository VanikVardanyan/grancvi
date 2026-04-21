from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master, Service
from src.services.booking import BookingService

YEREVAN = ZoneInfo("Asia/Yerevan")


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=6001,
        name="М",  # noqa: RUF001
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        slot_step_min=60,
        timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="К", phone="+37499555555")  # noqa: RUF001
    session.add(client)
    service = Service(master_id=master.id, name="Услуга", duration_min=60)
    session.add(service)
    await session.flush()
    return master, client, service


@pytest.mark.asyncio
async def test_get_month_load_empty_calendar(session: AsyncSession) -> None:
    master, _, service = await _seed(session)
    await session.commit()

    svc = BookingService(session)
    now = datetime(2026, 4, 1, 0, 0, tzinfo=YEREVAN)
    loads = await svc.get_month_load(
        master=master, service=service, month=date(2026, 5, 1), now=now
    )

    assert loads[date(2026, 5, 4)] == 9
    assert loads[date(2026, 5, 11)] == 9
    assert loads[date(2026, 5, 1)] == -1


@pytest.mark.asyncio
async def test_get_month_load_subtracts_existing_bookings(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    from src.repositories.appointments import AppointmentRepository

    repo = AppointmentRepository(session)
    await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=datetime(2026, 5, 4, 6, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        status="confirmed",
        source="client_request",
    )
    await session.commit()

    svc = BookingService(session)
    loads = await svc.get_month_load(
        master=master,
        service=service,
        month=date(2026, 5, 1),
        now=datetime(2026, 4, 1, 0, 0, tzinfo=YEREVAN),
    )
    assert loads[date(2026, 5, 4)] == 8


@pytest.mark.asyncio
async def test_list_client_history_delegates_to_repo(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    from src.repositories.appointments import AppointmentRepository

    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=datetime(2026, 3, 1, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 1, 8, 0, tzinfo=UTC),
        status="confirmed",
        source="client_request",
    )
    await session.commit()

    svc = BookingService(session)
    history = await svc.list_client_history(master, client.id, limit=10)
    assert [a.id for a in history] == [appt.id]
