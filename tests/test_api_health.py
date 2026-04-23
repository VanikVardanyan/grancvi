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


def test_cors_preflight_allows_app_origin() -> None:
    client = TestClient(app)
    r = client.options(
        "/v1/health",
        headers={
            "Origin": "https://app.jampord.am",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Telegram-Init-Data",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "https://app.jampord.am"


def test_cors_rejects_unknown_origin() -> None:
    client = TestClient(app)
    r = client.get("/v1/health", headers={"Origin": "https://evil.example.com"})
    # Request still succeeds (CORS is browser-enforced) but no allow-origin header.
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"
