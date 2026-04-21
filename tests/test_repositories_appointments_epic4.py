from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master, Service
from src.repositories.appointments import AppointmentRepository


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(tg_id=8001, name="М")  # noqa: RUF001
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="К", phone="+37499111111")  # noqa: RUF001
    session.add(client)
    service = Service(master_id=master.id, name="Услуга", duration_min=60)
    session.add(service)
    await session.flush()
    return master, client, service


@pytest.mark.asyncio
async def test_list_active_for_month_empty(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    await session.commit()

    repo = AppointmentRepository(session)
    start = datetime(2026, 5, 1, tzinfo=UTC)
    end = datetime(2026, 6, 1, tzinfo=UTC)
    assert (
        await repo.list_active_for_month(
            master.id, month_start_utc=start, month_end_utc=end
        )
        == []
    )


@pytest.mark.asyncio
async def test_list_active_for_month_filters_range_and_status(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)

    in_range = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 10, 8, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    pending = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 12, 11, 0, tzinfo=UTC),
        status="pending", source="client_request",
    )
    cancelled = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 15, 11, 0, tzinfo=UTC),
        status="cancelled", source="client_request",
    )
    before = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 4, 28, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 28, 11, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    after = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 6, 3, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 6, 3, 11, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    await session.commit()

    result = await repo.list_active_for_month(
        master.id,
        month_start_utc=datetime(2026, 5, 1, tzinfo=UTC),
        month_end_utc=datetime(2026, 6, 1, tzinfo=UTC),
    )
    ids = {a.id for a in result}
    assert ids == {in_range.id, pending.id}
    assert cancelled.id not in ids
    assert before.id not in ids
    assert after.id not in ids


@pytest.mark.asyncio
async def test_list_for_client_orders_desc_and_excludes_pending(
    session: AsyncSession,
) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)

    older = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    newer = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 1, 11, 0, tzinfo=UTC),
        status="cancelled", source="client_request",
    )
    still_pending = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 1, 11, 0, tzinfo=UTC),
        status="pending", source="client_request",
    )
    await session.commit()

    result = await repo.list_for_client(master.id, client.id, limit=10)
    ids = [a.id for a in result]
    assert ids == [newer.id, older.id]
    assert still_pending.id not in ids


@pytest.mark.asyncio
async def test_list_for_client_respects_limit(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)

    for i in range(5):
        await repo.create(
            master_id=master.id, client_id=client.id, service_id=service.id,
            start_at=datetime(2026, 1, i + 1, 10, 0, tzinfo=UTC),
            end_at=datetime(2026, 1, i + 1, 11, 0, tzinfo=UTC),
            status="confirmed", source="client_request",
        )
    await session.commit()

    result = await repo.list_for_client(master.id, client.id, limit=3)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_list_for_client_scoped_by_master(session: AsyncSession) -> None:
    master_a, client_a, _service_a = await _seed(session)
    master_b = Master(tg_id=8002, name="Другой")
    session.add(master_b)
    await session.flush()
    service_b = Service(master_id=master_b.id, name="Услуга", duration_min=60)
    session.add(service_b)
    client_b = Client(master_id=master_b.id, name="Тот же", phone=client_a.phone)
    session.add(client_b)
    await session.flush()

    repo = AppointmentRepository(session)
    await repo.create(
        master_id=master_b.id, client_id=client_b.id, service_id=service_b.id,
        start_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    await session.commit()

    result = await repo.list_for_client(master_a.id, client_a.id, limit=10)
    assert result == []
