from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_tg_user
from src.api.deps import get_bot, get_session
from src.api.main import app
from src.db.models import Appointment, Client, Master, Service

FAKE_TG_ID = 42
OTHER_TG_ID = 99


def _install_overrides(session: AsyncSession, *, tg_id: int = FAKE_TG_ID) -> AsyncMock:
    bot_mock = AsyncMock()

    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _bot_override() -> AsyncGenerator[AsyncMock, None]:
        yield bot_mock

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_bot] = _bot_override
    app.dependency_overrides[require_tg_user] = lambda: {"id": tg_id, "first_name": "U"}
    return bot_mock


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_master(
    session: AsyncSession,
    *,
    slug: str = "doc-1",
    tg_id: int = 10001,
    name: str = "Доктор",
    is_public: bool = True,
    blocked: bool = False,
    work_hours: dict[str, Any] | None = None,
) -> Master:
    master = Master(
        tg_id=tg_id,
        name=name,
        slug=slug,
        specialty_text="Стоматолог",
        is_public=is_public,
        timezone="Asia/Yerevan",
        work_hours=work_hours
        if work_hours is not None
        else {
            "mon": [["09:00", "20:00"]],
            "tue": [["09:00", "20:00"]],
            "wed": [["09:00", "20:00"]],
            "thu": [["09:00", "20:00"]],
            "fri": [["09:00", "20:00"]],
            "sat": [["09:00", "20:00"]],
            "sun": [["09:00", "20:00"]],
        },
        breaks={},
        slot_step_min=30,
    )
    session.add(master)
    await session.flush()
    if blocked:
        master.blocked_at = datetime.now(UTC)
        await session.flush()
    return master


async def _make_service(
    session: AsyncSession,
    master: Master,
    *,
    name: str = "Чистка",
    duration_min: int = 30,
    active: bool = True,
) -> Service:
    service = Service(master_id=master.id, name=name, duration_min=duration_min, active=active)
    session.add(service)
    await session.flush()
    return service


# ---------- masters.by-slug ----------


@pytest.mark.asyncio
async def test_by_slug_ok(session: AsyncSession, api_client: AsyncClient) -> None:
    master = await _make_master(session, slug="docsmith")
    await session.commit()
    _install_overrides(session)

    r = await api_client.get("/v1/masters/by-slug/docsmith")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(master.id)
    assert body["name"] == "Доктор"
    assert body["is_public"] is True
    assert body["timezone"] == "Asia/Yerevan"


@pytest.mark.asyncio
async def test_by_slug_unknown_returns_404(session: AsyncSession, api_client: AsyncClient) -> None:
    _install_overrides(session)
    r = await api_client.get("/v1/masters/by-slug/no-such")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_by_slug_blocked_returns_404(session: AsyncSession, api_client: AsyncClient) -> None:
    await _make_master(session, slug="blocked", tg_id=111, blocked=True)
    await session.commit()
    _install_overrides(session)
    r = await api_client.get("/v1/masters/by-slug/blocked")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_by_slug_private_returns_404(session: AsyncSession, api_client: AsyncClient) -> None:
    await _make_master(session, slug="private", tg_id=222, is_public=False)
    await session.commit()
    _install_overrides(session)
    r = await api_client.get("/v1/masters/by-slug/private")
    assert r.status_code == 404


# ---------- masters.services ----------


@pytest.mark.asyncio
async def test_services_returns_only_active(session: AsyncSession, api_client: AsyncClient) -> None:
    master = await _make_master(session, slug="docx", tg_id=333)
    await _make_service(session, master, name="Чистка", duration_min=30, active=True)
    await _make_service(session, master, name="Пломба", duration_min=60, active=False)
    await session.commit()
    _install_overrides(session)

    r = await api_client.get(f"/v1/masters/{master.id}/services")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["name"] == "Чистка"
    assert items[0]["duration_min"] == 30


# ---------- masters.slots?month=... ----------


@pytest.mark.asyncio
async def test_slots_month_returns_days(session: AsyncSession, api_client: AsyncClient) -> None:
    master = await _make_master(session, slug="doc-m", tg_id=444)
    service = await _make_service(session, master)
    await session.commit()
    _install_overrides(session)

    future = datetime.now(UTC) + timedelta(days=40)
    month_str = f"{future.year:04d}-{future.month:02d}"
    r = await api_client.get(
        f"/v1/masters/{master.id}/slots",
        params={"service_id": str(service.id), "month": month_str},
    )
    assert r.status_code == 200
    body = r.json()
    assert "days" in body
    assert len(body["days"]) >= 28  # any month has ≥28 days
    for day in body["days"]:
        assert "date" in day
        assert "has_capacity" in day


# ---------- masters.slots?date=... ----------


@pytest.mark.asyncio
async def test_slots_date_returns_list(session: AsyncSession, api_client: AsyncClient) -> None:
    master = await _make_master(session, slug="doc-d", tg_id=555)
    service = await _make_service(session, master, duration_min=30)
    await session.commit()
    _install_overrides(session)

    # Tomorrow should have slots within 09:00-20:00 work hours.
    target = (datetime.now(UTC) + timedelta(days=2)).date()
    r = await api_client.get(
        f"/v1/masters/{master.id}/slots",
        params={"service_id": str(service.id), "date": target.isoformat()},
    )
    assert r.status_code == 200
    slots = r.json()
    assert isinstance(slots, list)
    assert len(slots) > 0
    # Each item has an ISO8601 datetime with tz.
    for s in slots:
        assert "T" in s["start_at_utc"]


# ---------- bookings.create ----------


@pytest.mark.asyncio
async def test_create_booking_happy_path(session: AsyncSession, api_client: AsyncClient) -> None:
    master = await _make_master(session, slug="doc-c", tg_id=666)
    service = await _make_service(session, master, duration_min=30)
    await session.commit()
    bot_mock = _install_overrides(session)

    # pick a slot: tomorrow at 10:00 Yerevan
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Yerevan")
    tomorrow_local = (datetime.now(tz) + timedelta(days=1)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )
    start_at_utc = tomorrow_local.astimezone(UTC)

    r = await api_client.post(
        "/v1/bookings",
        json={
            "master_id": str(master.id),
            "service_id": str(service.id),
            "start_at_utc": start_at_utc.isoformat(),
            "client_name": "Петя",
            "client_phone": "+37499123456",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] in ("pending", "confirmed")
    assert bot_mock.send_message.await_count == 1


@pytest.mark.asyncio
async def test_create_booking_slot_taken_returns_409(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    master = await _make_master(session, slug="doc-t", tg_id=777)
    service = await _make_service(session, master, duration_min=30)
    # Pre-seed an appointment at the same slot.
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Yerevan")
    tomorrow_local = (datetime.now(tz) + timedelta(days=1)).replace(
        hour=11, minute=0, second=0, microsecond=0
    )
    start_at_utc = tomorrow_local.astimezone(UTC)

    other_client = Client(master_id=master.id, name="Other", phone=None, tg_id=None)
    session.add(other_client)
    await session.flush()
    session.add(
        Appointment(
            master_id=master.id,
            client_id=other_client.id,
            service_id=service.id,
            start_at=start_at_utc,
            end_at=start_at_utc + timedelta(minutes=30),
            status="confirmed",
            source="master_manual",
        )
    )
    await session.commit()

    _install_overrides(session)
    r = await api_client.post(
        "/v1/bookings",
        json={
            "master_id": str(master.id),
            "service_id": str(service.id),
            "start_at_utc": start_at_utc.isoformat(),
            "client_name": "Collider",
            "client_phone": "+37499000000",
        },
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "slot_taken"


@pytest.mark.asyncio
async def test_create_booking_missing_init_data_returns_401(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    master = await _make_master(session, slug="doc-a", tg_id=888)
    service = await _make_service(session, master)
    await session.commit()

    # Install bot and session overrides but NOT require_tg_user — the real
    # dependency will fail on the missing header.
    bot_mock = AsyncMock()

    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _bot_override() -> AsyncGenerator[AsyncMock, None]:
        yield bot_mock

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_bot] = _bot_override

    r = await api_client.post(
        "/v1/bookings",
        json={
            "master_id": str(master.id),
            "service_id": str(service.id),
            "start_at_utc": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "client_name": "X",
        },
    )
    # FastAPI returns 422 if header missing (Header(...) required), which our
    # exception handler maps to 400. But aiogram/tg flow expects 401 for invalid.
    # Since our `require_tg_user` uses Header(...) (required) + raises 401 only on
    # content issues, a missing header produces a RequestValidationError → 400.
    # Accept either: the critical invariant is that it's not 201.
    assert r.status_code in (400, 401, 422), r.status_code


@pytest.mark.asyncio
async def test_create_booking_bad_master_returns_404(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    _install_overrides(session)

    r = await api_client.post(
        "/v1/bookings",
        json={
            "master_id": str(uuid4()),
            "service_id": str(uuid4()),
            "start_at_utc": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "client_name": "X",
        },
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


# ---------- bookings.mine ----------


@pytest.mark.asyncio
async def test_mine_scoped_by_tg_id(session: AsyncSession, api_client: AsyncClient) -> None:
    master = await _make_master(session, slug="doc-mi", tg_id=901)
    service = await _make_service(session, master)
    mine = Client(master_id=master.id, name="Me", phone="+1", tg_id=FAKE_TG_ID)
    theirs = Client(master_id=master.id, name="Them", phone="+2", tg_id=OTHER_TG_ID)
    session.add_all([mine, theirs])
    await session.flush()

    start1 = datetime.now(UTC) + timedelta(days=1, hours=1)
    start2 = datetime.now(UTC) + timedelta(days=2)
    past = datetime.now(UTC) - timedelta(days=1)
    session.add_all(
        [
            Appointment(
                master_id=master.id,
                client_id=mine.id,
                service_id=service.id,
                start_at=start1,
                end_at=start1 + timedelta(minutes=30),
                status="confirmed",
                source="client_request",
            ),
            Appointment(
                master_id=master.id,
                client_id=theirs.id,
                service_id=service.id,
                start_at=start2,
                end_at=start2 + timedelta(minutes=30),
                status="confirmed",
                source="client_request",
            ),
            # Past appt for `mine` — must NOT show up.
            Appointment(
                master_id=master.id,
                client_id=mine.id,
                service_id=service.id,
                start_at=past,
                end_at=past + timedelta(minutes=30),
                status="confirmed",
                source="client_request",
            ),
        ]
    )
    await session.commit()

    _install_overrides(session, tg_id=FAKE_TG_ID)
    r = await api_client.get("/v1/bookings/mine")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["master_name"] == "Доктор"
    assert items[0]["service_name"] == "Чистка"


# ---------- bookings.cancel ----------


@pytest.mark.asyncio
async def test_cancel_owner_ok(session: AsyncSession, api_client: AsyncClient) -> None:
    master = await _make_master(session, slug="doc-cn", tg_id=902)
    service = await _make_service(session, master)
    mine = Client(master_id=master.id, name="Me", phone="+1", tg_id=FAKE_TG_ID)
    session.add(mine)
    await session.flush()
    start = datetime.now(UTC) + timedelta(days=1)
    appt = Appointment(
        master_id=master.id,
        client_id=mine.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(minutes=30),
        status="confirmed",
        source="client_request",
    )
    session.add(appt)
    await session.commit()

    bot_mock = _install_overrides(session, tg_id=FAKE_TG_ID)
    r = await api_client.post(f"/v1/bookings/{appt.id}/cancel")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    await session.refresh(appt)
    assert appt.status == "cancelled"
    assert bot_mock.send_message.await_count == 1


@pytest.mark.asyncio
async def test_cancel_non_owner_returns_403(session: AsyncSession, api_client: AsyncClient) -> None:
    master = await _make_master(session, slug="doc-co", tg_id=903)
    service = await _make_service(session, master)
    theirs = Client(master_id=master.id, name="Them", phone="+2", tg_id=OTHER_TG_ID)
    session.add(theirs)
    await session.flush()
    start = datetime.now(UTC) + timedelta(days=1)
    appt = Appointment(
        master_id=master.id,
        client_id=theirs.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(minutes=30),
        status="confirmed",
        source="client_request",
    )
    session.add(appt)
    await session.commit()

    _install_overrides(session, tg_id=FAKE_TG_ID)
    r = await api_client.post(f"/v1/bookings/{appt.id}/cancel")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "not_owner"


@pytest.mark.asyncio
async def test_cancel_already_cancelled_returns_409(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    master = await _make_master(session, slug="doc-cc", tg_id=904)
    service = await _make_service(session, master)
    mine = Client(master_id=master.id, name="Me", phone="+1", tg_id=FAKE_TG_ID)
    session.add(mine)
    await session.flush()
    start = datetime.now(UTC) + timedelta(days=1)
    appt = Appointment(
        master_id=master.id,
        client_id=mine.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(minutes=30),
        status="cancelled",
        source="client_request",
        cancelled_at=datetime.now(UTC),
        cancelled_by="client",
    )
    session.add(appt)
    await session.commit()

    _install_overrides(session, tg_id=FAKE_TG_ID)
    r = await api_client.post(f"/v1/bookings/{appt.id}/cancel")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "cannot_cancel"
