from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_tg_user
from src.api.deps import get_app_bot, get_bot, get_session
from src.api.main import app
from src.db.models import Salon


def _install_overrides(session: AsyncSession, *, tg_id: int) -> None:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    async def _bot_override() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    async def _app_bot_override() -> AsyncGenerator[None, None]:
        yield None

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_bot] = _bot_override
    app.dependency_overrides[get_app_bot] = _app_bot_override
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


@pytest.mark.asyncio
async def test_register_master_self_reserved_slug_returns_409(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    _install_overrides(session, tg_id=55001)
    r = await api_client.post(
        "/v1/register/master/self",
        json={
            "name": "Test Master",
            "specialty": "Парикмахер",
            "slug": "admin",
            "lang": "ru",
        },
    )
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "slug_reserved"


@pytest.mark.asyncio
async def test_register_salon_self_is_public_immediately(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    _install_overrides(session, tg_id=55002)
    r = await api_client.post(
        "/v1/register/salon/self",
        json={
            "name": "Test Salon",
            "slug": "test-salon-public",
        },
    )
    assert r.status_code == 201
    salon = await session.scalar(select(Salon).where(Salon.slug == "test-salon-public"))
    assert salon is not None
    assert salon.is_public is True


@pytest.mark.asyncio
async def test_register_master_self_succeeds_when_salon_exists(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    """Salon owner can register as master; master.salon_id auto-links to that salon."""
    from src.db.models import Master, Salon

    _install_overrides(session, tg_id=55003)

    salon_resp = await api_client.post(
        "/v1/register/salon/self",
        json={"name": "Dual Test Salon", "slug": "dual-test-salon"},
    )
    assert salon_resp.status_code == 201, salon_resp.json()

    master_resp = await api_client.post(
        "/v1/register/master/self",
        json={
            "name": "Dual Test Master",
            "specialty": "barber",
            "slug": "dual-test-master",
            "lang": "hy",
        },
    )
    assert master_resp.status_code == 201, master_resp.json()

    salon = await session.scalar(select(Salon).where(Salon.slug == "dual-test-salon"))
    master = await session.scalar(select(Master).where(Master.slug == "dual-test-master"))
    assert master is not None
    assert salon is not None
    assert master.salon_id == salon.id, "master.salon_id must auto-link to existing salon"


@pytest.mark.asyncio
async def test_register_salon_self_succeeds_when_master_exists(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    """Master can register as salon owner; master.salon_id back-fills to the new salon."""
    from src.db.models import Master, Salon

    _install_overrides(session, tg_id=55004)

    master_resp = await api_client.post(
        "/v1/register/master/self",
        json={
            "name": "Solo Master",
            "specialty": "barber",
            "slug": "solo-master-x",
            "lang": "hy",
        },
    )
    assert master_resp.status_code == 201, master_resp.json()

    salon_resp = await api_client.post(
        "/v1/register/salon/self",
        json={"name": "My Salon", "slug": "my-salon-x"},
    )
    assert salon_resp.status_code == 201, salon_resp.json()

    master = await session.scalar(select(Master).where(Master.slug == "solo-master-x"))
    salon = await session.scalar(select(Salon).where(Salon.slug == "my-salon-x"))
    assert master is not None
    assert salon is not None
    assert master.salon_id == salon.id, "existing master must auto-link to new salon"
