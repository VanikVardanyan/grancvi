"""Public web-booking API — read endpoint smoke tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.main import app
from src.db.models import Master, Service


def _install_session_override(session: AsyncSession) -> None:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = _session_override


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
