from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_tg_user
from src.api.deps import get_session
from src.api.main import app
from src.db.models import Master, Salon


def _install_overrides(session: AsyncSession, *, tg_id: int, first_name: str = "U") -> None:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[require_tg_user] = lambda: {
        "id": tg_id,
        "first_name": first_name,
    }


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_me_unknown_tg_id_is_client(session: AsyncSession, api_client: AsyncClient) -> None:
    _install_overrides(session, tg_id=555555, first_name="Guest")
    r = await api_client.get("/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "client"
    assert body["profile"]["tg_id"] == 555555
    assert body["profile"]["first_name"] == "Guest"
    assert body["profile"]["master_id"] is None
    assert body["profile"]["salon_id"] is None


@pytest.mark.asyncio
async def test_me_master_returns_master_profile(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    master = Master(
        tg_id=10001,
        name="Anna",
        slug="anna-1",
        specialty_text="Парикмахер",
    )
    session.add(master)
    await session.commit()

    _install_overrides(session, tg_id=10001, first_name="Anna")
    r = await api_client.get("/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "master"
    assert body["profile"]["master_id"] == str(master.id)
    assert body["profile"]["master_name"] == "Anna"
    assert body["profile"]["slug"] == "anna-1"
    assert body["profile"]["specialty"] == "Парикмахер"
    assert body["profile"]["salon_id"] is None


@pytest.mark.asyncio
async def test_me_salon_owner_returns_salon_profile(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    salon = Salon(owner_tg_id=777, name="Happy Salon", slug="happy")
    session.add(salon)
    await session.commit()

    _install_overrides(session, tg_id=777, first_name="Boss")
    r = await api_client.get("/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "salon_owner"
    assert body["profile"]["salon_id"] == str(salon.id)
    assert body["profile"]["salon_name"] == "Happy Salon"
    assert body["profile"]["slug"] == "happy"
    assert body["profile"]["master_id"] is None


@pytest.mark.asyncio
async def test_me_master_wins_when_tg_id_matches_both(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    """Dual-role: master takes precedence over salon_owner as the primary role."""
    salon = Salon(owner_tg_id=888, name="S", slug="s-888")
    session.add(salon)
    session.add(Master(tg_id=888, name="M", slug="m-888"))
    await session.commit()

    _install_overrides(session, tg_id=888)
    r = await api_client.get("/v1/me")
    body = r.json()
    assert body["role"] == "master"
    assert body["master_profile"] is not None
    assert body["salon_profile"] is not None


@pytest.mark.asyncio
async def test_me_returns_both_profiles_when_dual_role(
    session: AsyncSession, api_client: AsyncClient
) -> None:
    """Dual-role user gets both master_profile and salon_profile populated.

    Primary role = master.
    """
    salon = Salon(owner_tg_id=999, name="DR Salon", slug="dr-salon")
    session.add(salon)
    master = Master(tg_id=999, name="DR Master", slug="dr-master", specialty_text="barber")
    session.add(master)
    await session.commit()

    _install_overrides(session, tg_id=999, first_name="DR")
    r = await api_client.get("/v1/me")
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["role"] == "master", "primary role should be master when both exist"
    assert body["master_profile"] is not None
    assert body["master_profile"]["slug"] == "dr-master"
    assert body["master_profile"]["is_public"] is True
    assert body["salon_profile"] is not None
    assert body["salon_profile"]["slug"] == "dr-salon"
    assert body["salon_profile"]["is_public"] is True
