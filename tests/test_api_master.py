from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_tg_user
from src.api.deps import get_session
from src.api.main import app
from src.db.models import Appointment, Client, Master, Service


def _install_overrides(session: AsyncSession, *, tg_id: int) -> None:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[require_tg_user] = lambda: {
        "id": tg_id,
        "first_name": "U",
    }


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _seed(session: AsyncSession, *, tg_id: int = 7001) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=tg_id,
        name="M",
        slug=f"m-{tg_id}",
        specialty_text="Парикмахер",
        timezone="Asia/Yerevan",
        work_hours={"mon": [["10:00", "20:00"]]},
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Anna", phone="+1", tg_id=9001)
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=30)
    session.add(service)
    await session.flush()
    await session.commit()
    return master, client, service


@pytest.mark.asyncio
async def test_appointments_range_scoped_to_master(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    master, client, service = await _seed(session, tg_id=7001)
    other = Master(tg_id=7002, name="Other", slug="other-7002")
    session.add(other)
    await session.flush()
    other_client = Client(master_id=other.id, name="X", phone="+2")
    other_service = Service(master_id=other.id, name="Y", duration_min=30)
    session.add_all([other_client, other_service])
    await session.flush()

    today = datetime.now(UTC).astimezone().date()
    tomorrow = today + timedelta(days=1)
    mid = datetime(today.year, today.month, today.day, 12, 0, tzinfo=UTC)
    session.add_all(
        [
            Appointment(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at=mid,
                end_at=mid + timedelta(minutes=30),
                status="confirmed",
                source="client_request",
            ),
            # Out of range — day after tomorrow.
            Appointment(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at=mid + timedelta(days=3),
                end_at=mid + timedelta(days=3, minutes=30),
                status="confirmed",
                source="client_request",
            ),
            # Belongs to another master.
            Appointment(
                master_id=other.id,
                client_id=other_client.id,
                service_id=other_service.id,
                start_at=mid,
                end_at=mid + timedelta(minutes=30),
                status="confirmed",
                source="client_request",
            ),
            # Cancelled — filtered out.
            Appointment(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at=mid + timedelta(hours=2),
                end_at=mid + timedelta(hours=2, minutes=30),
                status="cancelled",
                source="client_request",
                cancelled_at=datetime.now(UTC),
                cancelled_by="client",
            ),
        ]
    )
    await session.commit()

    _install_overrides(session, tg_id=7001)
    r = await api_client.get(
        "/v1/master/me/appointments",
        params={"from": today.isoformat(), "to": tomorrow.isoformat()},
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["client_name"] == "Anna"
    assert items[0]["service_name"] == "Стрижка"
    assert items[0]["duration_min"] == 30
    assert items[0]["status"] == "confirmed"


@pytest.mark.asyncio
async def test_appointments_not_master_forbidden(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    _install_overrides(session, tg_id=9999999)
    r = await api_client.get(
        "/v1/master/me/appointments",
        params={"from": "2026-01-01", "to": "2026-01-02"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_appointments_blocked_master_forbidden(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    master, _, _ = await _seed(session, tg_id=7100)
    master.blocked_at = datetime.now(UTC)
    await session.commit()

    _install_overrides(session, tg_id=7100)
    r = await api_client.get(
        "/v1/master/me/appointments",
        params={"from": "2026-01-01", "to": "2026-01-02"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_appointments_bad_range(session: AsyncSession, api_client: AsyncClient) -> None:
    await _seed(session, tg_id=7200)
    _install_overrides(session, tg_id=7200)
    r = await api_client.get(
        "/v1/master/me/appointments",
        params={"from": "2026-02-01", "to": "2026-01-01"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_appointments_bad_date_format(session: AsyncSession, api_client: AsyncClient) -> None:
    await _seed(session, tg_id=7300)
    _install_overrides(session, tg_id=7300)
    r = await api_client.get(
        "/v1/master/me/appointments", params={"from": "bad", "to": "2026-01-02"}
    )
    assert r.status_code == 400
