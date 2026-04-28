from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_tg_user
from src.api.deps import get_app_bot, get_bot, get_session
from src.api.main import app


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
