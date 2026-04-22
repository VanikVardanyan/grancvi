from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master, Reminder, Service
from src.services.booking import BookingService
from src.services.reminders import ReminderService


@pytest.mark.asyncio
async def test_create_manual_with_reminder_service_schedules_three(
    session: AsyncSession,
) -> None:
    master = Master(tg_id=1, name="M", lang="ru", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, tg_id=2, name="C", phone="+37411000000")
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    reminder_svc = ReminderService(session)
    svc = BookingService(session, reminder_service=reminder_svc)

    start = datetime(2030, 5, 4, 12, 0, tzinfo=UTC)
    appt = await svc.create_manual(
        master=master,
        client=client,
        service=service,
        start_at=start,
        now=datetime(2030, 5, 1, 0, 0, tzinfo=UTC),
    )

    kinds = {r.kind for r in (await session.scalars(select(Reminder))).all()}
    assert kinds == {"day_before", "two_hours", "master_before"}
    assert appt.status == "confirmed"
