from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Appointment, Client, Master, Reminder, Service
from src.scheduler.jobs import send_due_reminders
from src.services.reminders import ReminderService


async def _seed_confirmed(
    session: AsyncSession, *, start_at: datetime
) -> tuple[Master, Client, Service, Appointment]:
    master = Master(tg_id=111, name="M", lang="ru", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, tg_id=222, name="Иван", phone="+37411000111")
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
    return master, client, service, appt


@pytest.mark.asyncio
async def test_sends_due_client_reminder(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    _, client, _, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(days=2))
    await session.commit()

    bot = AsyncMock()
    now = start - timedelta(hours=23)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == client.tg_id

    async with session_maker() as s:
        rows = list((await s.scalars(select(Reminder))).all())
        by_kind = {r.kind: r for r in rows}
        assert by_kind["day_before"].sent is True
        assert by_kind["two_hours"].sent is False
        assert by_kind["master_before"].sent is False


@pytest.mark.asyncio
async def test_skips_cancelled_appointment(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    _, _, _, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(days=2))
    appt.status = "cancelled"
    await session.commit()

    bot = AsyncMock()
    now = start - timedelta(hours=23)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    bot.send_message.assert_not_awaited()
    async with session_maker() as s:
        by_kind = {r.kind: r for r in (await s.scalars(select(Reminder))).all()}
        assert by_kind["day_before"].sent is True


@pytest.mark.asyncio
async def test_future_reminders_untouched(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    _, _, _, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(days=2))
    await session.commit()

    bot = AsyncMock()
    now = start - timedelta(days=3)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    bot.send_message.assert_not_awaited()
    async with session_maker() as s:
        assert all(r.sent is False for r in (await s.scalars(select(Reminder))).all())


@pytest.mark.asyncio
async def test_telegram_forbidden_marks_sent(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    _, _, _, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(days=2))
    await session.commit()

    bot = AsyncMock()
    bot.send_message.side_effect = TelegramBadRequest(method=Mock(), message="chat not found")

    now = start - timedelta(hours=23)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    async with session_maker() as s:
        by_kind = {r.kind: r for r in (await s.scalars(select(Reminder))).all()}
        assert by_kind["day_before"].sent is True


@pytest.mark.asyncio
async def test_master_reminder_goes_to_master_chat(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    master, _, _, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(minutes=30))
    await session.commit()

    bot = AsyncMock()
    now = start - timedelta(minutes=10)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == master.tg_id
    assert "Иван" in kwargs["text"]
    assert "Стрижка" in kwargs["text"]


@pytest.mark.asyncio
async def test_idempotent_second_run_no_resend(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    _, _, _, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(days=2))
    await session.commit()

    bot = AsyncMock()
    now = start - timedelta(hours=23)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    assert bot.send_message.await_count == 1
