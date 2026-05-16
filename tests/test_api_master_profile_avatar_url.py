from __future__ import annotations

import io
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_tg_user
from src.api.deps import get_session
from src.api.main import app
from src.config import settings
from src.db.models import Master


def _png(size: int = 80) -> bytes:
    img = Image.new("RGB", (size, size), (5, 80, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _install_overrides(session: AsyncSession, *, tg_id: int) -> None:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[require_tg_user] = lambda: {"id": tg_id, "first_name": "T"}


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_profile_avatar_url_null_then_set(
    session: AsyncSession,
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "avatars_dir", str(tmp_path))
    master = Master(tg_id=92010, name="Av Url", slug="av-url-92010")
    session.add(master)
    await session.flush()
    await session.commit()
    _install_overrides(session, tg_id=92010)

    r = await api_client.get("/v1/master/me/profile")
    assert r.status_code == 200, r.text
    assert r.json()["avatar_url"] is None

    up = await api_client.post(
        "/v1/master/me/avatar",
        files={"file": ("a.png", _png(), "image/png")},
    )
    assert up.status_code == 200, up.text
    r2 = await api_client.get("/v1/master/me/profile")
    url = r2.json()["avatar_url"]
    assert url is not None and str(master.id) in url and "?v=" in url


@pytest.mark.asyncio
async def test_by_slug_master_exposes_avatar_url_field(
    session: AsyncSession,
    api_client: AsyncClient,
) -> None:
    master = Master(tg_id=92011, name="Bs Url", slug="bs-url-92011", is_public=True)
    session.add(master)
    await session.flush()
    await session.commit()

    r = await api_client.get("/v1/masters/by-slug/bs-url-92011")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "avatar_url" in body
    assert body["avatar_url"] is None
