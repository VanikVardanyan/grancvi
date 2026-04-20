from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master, Service
from src.services.booking import BookingService


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=9001,
        name="Мастер",
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        slot_step_min=60,
        timezone="Asia/Yerevan",
        decision_timeout_min=120,
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="К", phone="+37490000042")  # noqa: RUF001
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()
    return master, client, service


@pytest.mark.asyncio
async def test_get_free_slots_empty_day(session: AsyncSession) -> None:
    master, _, service = await _seed(session)
    await session.commit()

    svc = BookingService(session)
    result = await svc.get_free_slots(master, service, date(2026, 4, 20))
    assert [s.hour for s in result] == [10, 11, 12, 13, 14, 15, 16, 17, 18]


@pytest.mark.asyncio
async def test_get_free_slots_excludes_existing_booking(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    # Existing confirmed booking 13:00-14:00 Yerevan = 09:00-10:00 UTC
    from src.repositories.appointments import AppointmentRepository

    repo = AppointmentRepository(session)
    await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=datetime(2026, 4, 20, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
        status="confirmed",
        source="client_request",
    )
    await session.commit()

    svc = BookingService(session)
    result = await svc.get_free_slots(master, service, date(2026, 4, 20))
    assert [s.hour for s in result] == [10, 11, 12, 14, 15, 16, 17, 18]


@pytest.mark.asyncio
async def test_get_free_slots_respects_now_filter(session: AsyncSession) -> None:
    master, _, service = await _seed(session)
    await session.commit()

    # 14:30 Yerevan on the same day
    from zoneinfo import ZoneInfo

    now = datetime(2026, 4, 20, 14, 30, tzinfo=ZoneInfo("Asia/Yerevan"))
    svc = BookingService(session)
    result = await svc.get_free_slots(master, service, date(2026, 4, 20), now=now)
    assert [s.hour for s in result] == [15, 16, 17, 18]
