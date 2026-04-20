from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Client, Master, Service
from src.exceptions import InvalidState, NotFound, SlotAlreadyTaken
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


@pytest.mark.asyncio
async def test_create_pending_persists_with_decision_deadline(
    session: AsyncSession,
) -> None:
    master, client, service = await _seed(session)
    await session.commit()

    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    now = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
    svc = BookingService(session)
    appt = await svc.create_pending(
        master=master, client=client, service=service, start_at=start, now=now
    )

    assert appt.status == "pending"
    assert appt.source == "client_request"
    assert appt.start_at == start
    assert appt.end_at == start + timedelta(minutes=service.duration_min)
    # decision_deadline = now + 120 min (master.decision_timeout_min)
    assert appt.decision_deadline == now + timedelta(minutes=master.decision_timeout_min)


@pytest.mark.asyncio
async def test_create_pending_rejects_duplicate(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()

    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    svc = BookingService(session)
    await svc.create_pending(master=master, client=client, service=service, start_at=start)

    # Re-use the same session — the second insert hits IntegrityError and becomes SlotAlreadyTaken
    with pytest.raises(SlotAlreadyTaken):
        await svc.create_pending(master=master, client=client, service=service, start_at=start)


@pytest.mark.asyncio
async def test_create_pending_race_one_wins_one_loses(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    # Seed master/client/service via the per-test `session` fixture and commit
    master, client, service = await _seed(session)
    await session.commit()
    # Close the seed session so it doesn't hold locks
    await session.close()

    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)

    async def attempt() -> object:
        async with session_maker() as s:
            svc = BookingService(s)
            try:
                return await svc.create_pending(
                    master=master, client=client, service=service, start_at=start
                )
            except SlotAlreadyTaken as exc:
                return exc

    a, b = await asyncio.gather(attempt(), attempt())
    from src.db.models import Appointment

    wins = [r for r in (a, b) if isinstance(r, Appointment)]
    losses = [r for r in (a, b) if isinstance(r, SlotAlreadyTaken)]
    assert len(wins) == 1
    assert len(losses) == 1


@pytest.mark.asyncio
async def test_confirm_sets_status_and_confirmed_at(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(master=master, client=client, service=service, start_at=start)

    confirmed_at = datetime(2026, 4, 20, 8, 30, tzinfo=UTC)
    result = await svc.confirm(appt.id, master_id=master.id, now=confirmed_at)
    assert result.status == "confirmed"
    assert result.confirmed_at == confirmed_at


@pytest.mark.asyncio
async def test_confirm_missing_raises_not_found(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    with pytest.raises(NotFound):
        await svc.confirm(uuid4(), master_id=master.id)


@pytest.mark.asyncio
async def test_confirm_non_pending_raises_invalid_state(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(master=master, client=client, service=service, start_at=start)
    await svc.confirm(appt.id, master_id=master.id)

    with pytest.raises(InvalidState):
        await svc.confirm(appt.id, master_id=master.id)


@pytest.mark.asyncio
async def test_reject_sets_status_and_appends_reason(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(master=master, client=client, service=service, start_at=start)

    result = await svc.reject(appt.id, master_id=master.id, reason="занят")
    assert result.status == "rejected"
    assert result.comment == "занят"


@pytest.mark.asyncio
async def test_reject_non_pending_raises_invalid_state(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(master=master, client=client, service=service, start_at=start)
    await svc.reject(appt.id, master_id=master.id)

    with pytest.raises(InvalidState):
        await svc.reject(appt.id, master_id=master.id)


@pytest.mark.asyncio
async def test_cancel_by_client_sets_fields(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(master=master, client=client, service=service, start_at=start)
    await svc.confirm(appt.id, master_id=master.id)

    cancelled_at = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
    result = await svc.cancel(appt.id, cancelled_by="client", now=cancelled_at)
    assert result.status == "cancelled"
    assert result.cancelled_at == cancelled_at
    assert result.cancelled_by == "client"


@pytest.mark.asyncio
async def test_cancel_invalid_cancelled_by_raises_value_error(
    session: AsyncSession,
) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(master=master, client=client, service=service, start_at=start)
    with pytest.raises(ValueError):
        await svc.cancel(appt.id, cancelled_by="nobody")


@pytest.mark.asyncio
async def test_cancel_terminal_status_raises_invalid_state(
    session: AsyncSession,
) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(master=master, client=client, service=service, start_at=start)
    await svc.cancel(appt.id, cancelled_by="client")

    with pytest.raises(InvalidState):
        await svc.cancel(appt.id, cancelled_by="client")


@pytest.mark.asyncio
async def test_create_manual_is_instantly_confirmed(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    now = datetime(2026, 4, 20, 7, 0, tzinfo=UTC)

    appt = await svc.create_manual(
        master=master,
        client=client,
        service=service,
        start_at=start,
        comment="клиент позвонил",
        now=now,
    )
    assert appt.status == "confirmed"
    assert appt.source == "master_manual"
    assert appt.confirmed_at == now
    assert appt.comment == "клиент позвонил"
    assert appt.end_at == start + timedelta(minutes=service.duration_min)


@pytest.mark.asyncio
async def test_create_manual_rejects_if_slot_taken(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    await svc.create_manual(master=master, client=client, service=service, start_at=start)

    with pytest.raises(SlotAlreadyTaken):
        await svc.create_manual(master=master, client=client, service=service, start_at=start)


@pytest.mark.asyncio
async def test_create_manual_race_one_wins_one_loses(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    await session.close()

    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)

    async def attempt() -> object:
        async with session_maker() as s:
            svc = BookingService(s)
            try:
                return await svc.create_manual(
                    master=master, client=client, service=service, start_at=start
                )
            except SlotAlreadyTaken as exc:
                return exc

    a, b = await asyncio.gather(attempt(), attempt())
    from src.db.models import Appointment

    wins = [r for r in (a, b) if isinstance(r, Appointment)]
    losses = [r for r in (a, b) if isinstance(r, SlotAlreadyTaken)]
    assert len(wins) == 1
    assert len(losses) == 1
