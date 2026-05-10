from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.deps import get_session
from src.api.main import app
from src.db.models import Master, Salon
from src.repositories.masters import MasterRepository


@pytest.mark.asyncio
async def test_public_master_avatar_url_null_when_no_avatar(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    repo = MasterRepository(session)
    master = await repo.create(tg_id=42001, name="A")
    master.slug = "alpha-master"
    master.is_public = True
    await session.commit()

    async def _override():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/v1/public/masters/alpha-master")
            assert r.status_code == 200
            assert r.json()["avatar_url"] is None
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_public_master_avatar_url_present_when_uploaded(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    repo = MasterRepository(session)
    master = await repo.create(tg_id=42002, name="B")
    master.slug = "beta-master"
    master.is_public = True
    ts = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    master.avatar_uploaded_at = ts
    await session.commit()

    async def _override():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/v1/public/masters/beta-master")
            assert r.status_code == 200
            data = r.json()
            assert data["avatar_url"] is not None
            assert str(master.id) in data["avatar_url"]
            assert data["avatar_url"].endswith(f"?v={int(ts.timestamp())}")
            assert "/static/avatars/" in data["avatar_url"]
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_public_salon_lists_master_avatar_url(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    salon = Salon(slug="my-salon", name="My Salon", is_public=True, owner_tg_id=99001)
    session.add(salon)
    await session.flush()

    repo = MasterRepository(session)
    master = await repo.create(tg_id=42003, name="C")
    master.slug = "gamma-master"
    master.is_public = True
    master.salon_id = salon.id
    ts = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    master.avatar_uploaded_at = ts
    await session.commit()

    async def _override():
        async with session_maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/v1/public/salons/my-salon")
            assert r.status_code == 200
            masters = r.json()["masters"]
            assert len(masters) == 1
            assert masters[0]["avatar_url"] is not None
            assert masters[0]["avatar_url"].endswith(f"?v={int(ts.timestamp())}")
    finally:
        app.dependency_overrides.pop(get_session, None)
