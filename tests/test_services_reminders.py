from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Reminder, Service
from src.services.reminders import ReminderService


async def _seed_appt(session: AsyncSession, *, start_at: datetime) -> Appointment:
    master = Master(tg_id=100, name="M", lang="ru", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, tg_id=200, name="C", phone="+37411000000")
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()

    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=60),
        status="confirmed",
        source="client_request",
    )
    session.add(appt)
    await session.flush()
    return appt


@pytest.mark.asyncio
async def test_schedule_creates_three_reminders_when_all_future(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    now = start - timedelta(days=2)
    appt = await _seed_appt(session, start_at=start)

    svc = ReminderService(session)
    count = await svc.schedule_for_appointment(appt, now=now)

    assert count == 3
    rows = list((await session.scalars(select(Reminder))).all())
    by_kind = {r.kind: r for r in rows}
    assert set(by_kind) == {"day_before", "two_hours", "master_before"}
    assert by_kind["day_before"].send_at == start - timedelta(hours=24)
    assert by_kind["two_hours"].send_at == start - timedelta(hours=2)
    assert by_kind["master_before"].send_at == start - timedelta(minutes=15)


@pytest.mark.asyncio
async def test_schedule_skips_day_before_when_less_than_24h(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    now = start - timedelta(hours=20)
    appt = await _seed_appt(session, start_at=start)

    svc = ReminderService(session)
    count = await svc.schedule_for_appointment(appt, now=now)

    assert count == 2
    kinds = {r.kind for r in (await session.scalars(select(Reminder))).all()}
    assert kinds == {"two_hours", "master_before"}


@pytest.mark.asyncio
async def test_schedule_skips_all_when_less_than_15min(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    now = start - timedelta(minutes=10)
    appt = await _seed_appt(session, start_at=start)

    svc = ReminderService(session)
    count = await svc.schedule_for_appointment(appt, now=now)

    assert count == 0
    assert list((await session.scalars(select(Reminder))).all()) == []


@pytest.mark.asyncio
async def test_schedule_is_idempotent(session: AsyncSession) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    now = start - timedelta(days=2)
    appt = await _seed_appt(session, start_at=start)

    svc = ReminderService(session)
    await svc.schedule_for_appointment(appt, now=now)
    second = await svc.schedule_for_appointment(appt, now=now)

    assert second == 0
    rows = list((await session.scalars(select(Reminder))).all())
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_suppress_marks_all_unsent(session: AsyncSession) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    now = start - timedelta(days=2)
    appt = await _seed_appt(session, start_at=start)

    svc = ReminderService(session)
    await svc.schedule_for_appointment(appt, now=now)

    suppress_now = start - timedelta(hours=23)
    count = await svc.suppress_for_appointment(appt.id, now=suppress_now)

    assert count == 3
    rows = list((await session.scalars(select(Reminder))).all())
    for r in rows:
        assert r.sent is True
        assert r.sent_at == suppress_now


@pytest.mark.asyncio
async def test_suppress_no_op_when_no_reminders(session: AsyncSession) -> None:
    svc = ReminderService(session)
    count = await svc.suppress_for_appointment(uuid4(), now=datetime.now(UTC))
    assert count == 0
