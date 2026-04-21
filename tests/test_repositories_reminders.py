from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Reminder, Service
from src.repositories.reminders import ReminderRepository


async def _seed_appt(
    session: AsyncSession,
    *,
    start_at: datetime = datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
    status: str = "confirmed",
) -> tuple[Master, Client, Service, Appointment]:
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
        status=status,
        source="client_request",
    )
    session.add(appt)
    await session.flush()
    return master, client, service, appt


@pytest.mark.asyncio
async def test_insert_many_persists_rows(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    send_at = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)

    count = await repo.insert_many(
        [
            (appt.id, "day_before", send_at),
            (appt.id, "two_hours", send_at + timedelta(hours=22)),
        ]
    )

    assert count == 2
    rows = list((await session.scalars(select(Reminder))).all())
    assert len(rows) == 2
    kinds = {r.kind for r in rows}
    assert kinds == {"day_before", "two_hours"}
    assert all(r.sent is False for r in rows)


@pytest.mark.asyncio
async def test_insert_many_idempotent_on_duplicate(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    send_at = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)

    await repo.insert_many([(appt.id, "day_before", send_at)])
    count = await repo.insert_many([(appt.id, "day_before", send_at + timedelta(hours=1))])

    assert count == 0
    rows = list((await session.scalars(select(Reminder))).all())
    assert len(rows) == 1
    assert rows[0].send_at == send_at


@pytest.mark.asyncio
async def test_get_due_for_update_returns_only_due_unsent(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    base = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    await repo.insert_many(
        [
            (appt.id, "day_before", base - timedelta(hours=1)),
            (appt.id, "two_hours", base + timedelta(hours=1)),
        ]
    )
    await session.commit()

    rows = await repo.get_due_for_update(now=base, limit=100)
    assert len(rows) == 1
    reminder, appt_row, master_row, client_row, service_row = rows[0]
    assert reminder.kind == "day_before"
    assert appt_row.id == appt.id
    assert master_row.id == appt.master_id
    assert client_row.id == appt.client_id
    assert service_row.id == appt.service_id


@pytest.mark.asyncio
async def test_get_due_for_update_skips_sent(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    base = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    await repo.insert_many([(appt.id, "day_before", base - timedelta(hours=1))])
    await session.commit()

    reminder = (await session.scalars(select(Reminder))).one()
    await repo.mark_sent(reminder.id, sent_at=base)
    await session.commit()

    rows = await repo.get_due_for_update(now=base, limit=100)
    assert rows == []


@pytest.mark.asyncio
async def test_mark_sent_sets_sent_true_and_timestamp(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    send_at = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)

    await repo.insert_many([(appt.id, "day_before", send_at)])
    await session.commit()

    reminder = (await session.scalars(select(Reminder))).one()
    now = datetime(2026, 5, 3, 12, 0, 30, tzinfo=UTC)
    await repo.mark_sent(reminder.id, sent_at=now)

    await session.refresh(reminder)
    assert reminder.sent is True
    assert reminder.sent_at == now


@pytest.mark.asyncio
async def test_suppress_for_appointment_only_marks_unsent(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    base = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    await repo.insert_many(
        [
            (appt.id, "day_before", base - timedelta(hours=1)),
            (appt.id, "two_hours", base + timedelta(hours=1)),
            (appt.id, "master_before", base + timedelta(hours=2)),
        ]
    )
    await session.commit()

    already_sent = (
        await session.scalars(select(Reminder).where(Reminder.kind == "day_before"))
    ).one()
    already_sent.sent = True
    already_sent.sent_at = base - timedelta(minutes=30)
    await session.commit()

    count = await repo.suppress_for_appointment(appt.id, now=base)
    assert count == 2

    all_rows = list((await session.scalars(select(Reminder))).all())
    for r in all_rows:
        assert r.sent is True
    still = next(r for r in all_rows if r.kind == "day_before")
    assert still.sent_at == base - timedelta(minutes=30)
