from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio
from fastapi.testclient import TestClient

from src.api.main import app


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables() -> AsyncGenerator[None, None]:
    """Override DB-truncation fixture — API tests are stateless here."""
    yield


def test_health_endpoint() -> None:
    client = TestClient(app)
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
