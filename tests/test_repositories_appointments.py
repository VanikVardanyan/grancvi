from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master, Service
from src.repositories.appointments import AppointmentRepository


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(tg_id=1001, name="Анна")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Клиент", phone="+37490000001")
    session.add(client)
    service = Service(master_id=master.id, name="Чистка", duration_min=60)
    session.add(service)
    await session.flush()
    return master, client, service


@pytest.mark.asyncio
async def test_create_persists_row(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    start = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)

    appt = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status="pending",
        source="client_request",
    )
    await session.commit()

    assert appt.id is not None
    refreshed = await repo.get(appt.id)
    assert refreshed is not None
    assert refreshed.status == "pending"
    assert refreshed.start_at == start


@pytest.mark.asyncio
async def test_list_active_for_day_returns_only_overlapping(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)

    def at(hour: int) -> datetime:
        return datetime(2026, 4, 20, hour, 0, tzinfo=UTC)

    # On the day, pending — should appear
    a = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=at(6),
        end_at=at(7),
        status="pending",
        source="client_request",
    )
    # On the day, confirmed — should appear
    b = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=at(10),
        end_at=at(11),
        status="confirmed",
        source="client_request",
    )
    # On the day, cancelled — must NOT appear
    await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=at(12),
        end_at=at(13),
        status="cancelled",
        source="client_request",
    )
    # On previous day — must NOT appear
    await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        status="confirmed",
        source="client_request",
    )
    await session.commit()

    day_start = datetime(2026, 4, 20, 0, 0, tzinfo=UTC)
    day_end = datetime(2026, 4, 21, 0, 0, tzinfo=UTC)
    result = await repo.list_active_for_day(master.id, day_start_utc=day_start, day_end_utc=day_end)
    assert {r.id for r in result} == {a.id, b.id}


@pytest.mark.asyncio
async def test_get_scoped_by_master_returns_none_for_other_master(
    session: AsyncSession,
) -> None:
    master, client, service = await _seed(session)
    other = Master(tg_id=2002, name="Борис")
    session.add(other)
    await session.flush()

    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 20, 11, 0, tzinfo=UTC),
        status="pending",
        source="client_request",
    )
    await session.commit()

    assert await repo.get(appt.id, master_id=other.id) is None
    assert (await repo.get(appt.id, master_id=master.id)) is not None


@pytest.mark.asyncio
async def test_update_status_writes_through(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    start = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)
    appt = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status="pending",
        source="client_request",
    )
    await session.commit()

    confirmed_at = datetime(2026, 4, 20, 9, 30, tzinfo=UTC)
    result = await repo.update_status(
        appt.id, master_id=master.id, status="confirmed", confirmed_at=confirmed_at
    )
    await session.commit()
    assert result is not None
    assert result.status == "confirmed"
    assert result.confirmed_at == confirmed_at


@pytest.mark.asyncio
async def test_update_status_other_master_returns_none(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    other = Master(tg_id=3003, name="Валерий")
    session.add(other)
    await session.flush()
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 20, 11, 0, tzinfo=UTC),
        status="pending",
        source="client_request",
    )
    await session.commit()

    result = await repo.update_status(appt.id, master_id=other.id, status="confirmed")
    assert result is None
    # Still pending after the no-op
    refreshed = await repo.get(appt.id)
    assert refreshed is not None
    assert refreshed.status == "pending"


@pytest.mark.asyncio
async def test_get_pending_past_deadline_filters(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)

    def at(hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 4, 20, hour, minute, tzinfo=UTC)

    # Past deadline — should appear
    stale = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=at(15),
        end_at=at(16),
        status="pending",
        source="client_request",
        decision_deadline=at(10),
    )
    # Future deadline — must NOT appear
    await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=at(17),
        end_at=at(18),
        status="pending",
        source="client_request",
        decision_deadline=at(23),
    )
    # Not pending — must NOT appear
    await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=at(18),
        end_at=at(19),
        status="confirmed",
        source="client_request",
        decision_deadline=at(9),
    )
    await session.commit()

    now = at(12)
    result = await repo.get_pending_past_deadline(now=now)
    assert {r.id for r in result} == {stale.id}


@pytest.mark.asyncio
async def test_partial_unique_allows_cancelled_reinsert(session: AsyncSession) -> None:
    """The partial unique index only covers pending+confirmed — cancelled slots free up."""
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    start = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)

    # First booking, then cancel it
    first = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status="pending",
        source="client_request",
    )
    await session.commit()

    await repo.update_status(first.id, master_id=master.id, status="cancelled")
    await session.commit()

    # Same slot, new booking — must succeed
    second = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status="pending",
        source="client_request",
    )
    await session.commit()
    assert second.id != first.id


@pytest.mark.asyncio
async def test_partial_unique_rejects_duplicate_pending(session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    start = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)

    await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status="pending",
        source="client_request",
    )
    await session.commit()

    with pytest.raises(IntegrityError):
        await repo.create(
            master_id=master.id,
            client_id=client.id,
            service_id=service.id,
            start_at=start,
            end_at=start + timedelta(minutes=60),
            status="pending",
            source="client_request",
        )
        await session.commit()
