"""Public web-booking API — read endpoint smoke tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis as _Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_app_bot, get_bot, get_session
from src.api.main import app
from src.db.models import Master, Service


def _install_session_override(session: AsyncSession) -> None:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = _session_override


async def _no_bot() -> AsyncGenerator[None, None]:
    yield None


def _install_bot_overrides() -> None:
    """Override both bot deps to avoid real Telegram token validation."""

    async def _null_bot() -> AsyncGenerator[None, None]:
        yield None

    app.dependency_overrides[get_bot] = _null_bot
    app.dependency_overrides[get_app_bot] = _null_bot


@pytest_asyncio.fixture(autouse=True)
async def _set_app_redis() -> AsyncGenerator[None, None]:
    """Attach a test Redis client to app.state and flush stale rate-limit keys."""
    redis = _Redis.from_url("redis://localhost:6379/9", decode_responses=False)
    await redis.flushdb()
    app.state.redis = redis
    yield
    await redis.aclose()


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_public_get_master_returns_profile(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    _install_session_override(session)
    master = Master(
        tg_id=88001,
        name="Public Anna",
        slug="public-anna",
        specialty_text="hairdresser_women",
        lang="hy",
        work_hours={"mon": [["09:00", "20:00"]]},
        is_public=True,
    )
    session.add(master)
    await session.commit()

    r = await api_client.get("/v1/public/masters/public-anna")
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["name"] == "Public Anna"
    assert body["slug"] == "public-anna"
    assert body["lang"] == "hy"


@pytest.mark.asyncio
async def test_public_get_master_404_when_blocked(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    _install_session_override(session)
    from src.utils.time import now_utc

    master = Master(
        tg_id=88002,
        name="Blocked",
        slug="blocked-anna",
        specialty_text="x",
        lang="ru",
        work_hours={"mon": [["09:00", "20:00"]]},
        is_public=True,
        blocked_at=now_utc(),
    )
    session.add(master)
    await session.commit()

    r = await api_client.get("/v1/public/masters/blocked-anna")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_public_list_services_returns_active(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    _install_session_override(session)
    master = Master(
        tg_id=88003,
        name="Svc Anna",
        slug="svc-anna",
        specialty_text="x",
        lang="ru",
        work_hours={"mon": [["09:00", "20:00"]]},
        is_public=True,
    )
    session.add(master)
    await session.flush()
    s_active = Service(master_id=master.id, name="Active", duration_min=60, active=True)
    s_inactive = Service(master_id=master.id, name="Old", duration_min=60, active=False)
    session.add_all([s_active, s_inactive])
    await session.commit()

    r = await api_client.get("/v1/public/masters/svc-anna/services")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["name"] == "Active"


@pytest.mark.asyncio
async def test_public_create_booking_happy_path(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    """End-to-end: master + service exist → POST creates pending appointment."""
    _install_session_override(session)
    _install_bot_overrides()
    master = Master(
        tg_id=88010,
        name="Booking Anna",
        slug="booking-anna",
        specialty_text="x",
        lang="ru",
        work_hours={
            "mon": [["09:00", "20:00"]],
            "tue": [["09:00", "20:00"]],
            "wed": [["09:00", "20:00"]],
            "thu": [["09:00", "20:00"]],
            "fri": [["09:00", "20:00"]],
            "sat": [["09:00", "20:00"]],
        },
        is_public=True,
    )
    session.add(master)
    await session.flush()
    svc = Service(master_id=master.id, name="Cut", duration_min=60, active=True)
    session.add(svc)
    await session.commit()

    today = datetime.now(UTC)
    days_to_mon = (7 - today.weekday()) % 7 or 7
    monday = (today + timedelta(days=days_to_mon)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )

    r = await api_client.post(
        "/v1/public/bookings",
        json={
            "master_slug": "booking-anna",
            "service_id": str(svc.id),
            "start_at_utc": monday.isoformat(),
            "client_name": "Mariam",
            "client_phone": "+37493144550",
            "recaptcha_token": None,
        },
    )
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["status"] == "pending"
    assert UUID(body["id"])
    assert body["telegram_link_url"].startswith("https://t.me/")
    assert "?start=link_" in body["telegram_link_url"]


@pytest.mark.asyncio
async def test_public_create_booking_404_unknown_slug(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    _install_session_override(session)
    _install_bot_overrides()
    r = await api_client.post(
        "/v1/public/bookings",
        json={
            "master_slug": "no-such-master",
            "service_id": "00000000-0000-0000-0000-000000000000",
            "start_at_utc": "2099-01-01T10:00:00Z",
            "client_name": "X",
            "client_phone": "+37499000000",
            "recaptcha_token": None,
        },
    )
    assert r.status_code == 404
