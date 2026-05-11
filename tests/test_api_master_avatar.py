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


def _png(size: int = 200) -> bytes:
    """Generate a small valid PNG image in memory."""
    img = Image.new("RGB", (size, size), (10, 100, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _install_overrides(session: AsyncSession, *, tg_id: int) -> None:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[require_tg_user] = lambda: {
        "id": tg_id,
        "first_name": "T",
    }


@pytest_asyncio.fixture
async def api_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_master(session: AsyncSession, *, tg_id: int) -> Master:
    master = Master(tg_id=tg_id, name="Avatar Tester", slug=f"avatar-test-{tg_id}")
    session.add(master)
    await session.flush()
    await session.commit()
    return master


# ---------- happy path ----------


@pytest.mark.asyncio
async def test_upload_avatar_happy_path(
    session: AsyncSession,
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "avatars_dir", str(tmp_path))
    master = await _make_master(session, tg_id=91001)
    _install_overrides(session, tg_id=91001)

    r = await api_client.post(
        "/v1/master/me/avatar",
        files={"file": ("avatar.png", _png(), "image/png")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "avatar_url" in body
    url: str = body["avatar_url"]
    assert str(master.id) in url
    assert "/static/avatars/" in url
    assert "?v=" in url

    # File must exist on disk
    avatar_file = tmp_path / f"{master.id}.jpg"
    assert avatar_file.exists()

    # DB column must be non-null
    await session.refresh(master)
    assert master.avatar_uploaded_at is not None


# ---------- oversize ----------


@pytest.mark.asyncio
async def test_upload_avatar_too_large(
    session: AsyncSession,
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "avatars_dir", str(tmp_path))
    await _make_master(session, tg_id=91002)
    _install_overrides(session, tg_id=91002)

    oversize = b"X" * (11 * 1024 * 1024)  # 11 MB of garbage bytes
    r = await api_client.post(
        "/v1/master/me/avatar",
        files={"file": ("big.bin", oversize, "application/octet-stream")},
    )
    assert r.status_code == 413, r.text
    assert r.json()["error"]["code"] == "avatar_too_large"


# ---------- bad image ----------


@pytest.mark.asyncio
async def test_upload_avatar_bad_image(
    session: AsyncSession,
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "avatars_dir", str(tmp_path))
    await _make_master(session, tg_id=91003)
    _install_overrides(session, tg_id=91003)

    r = await api_client.post(
        "/v1/master/me/avatar",
        files={"file": ("broken.png", b"not an image at all", "image/png")},
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "bad_image"


# ---------- delete after upload ----------


@pytest.mark.asyncio
async def test_delete_avatar_after_upload(
    session: AsyncSession,
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "avatars_dir", str(tmp_path))
    master = await _make_master(session, tg_id=91004)
    _install_overrides(session, tg_id=91004)

    # Upload first
    r = await api_client.post(
        "/v1/master/me/avatar",
        files={"file": ("avatar.png", _png(), "image/png")},
    )
    assert r.status_code == 200, r.text

    # Now delete
    r = await api_client.delete("/v1/master/me/avatar")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    # File must be gone
    assert not (tmp_path / f"{master.id}.jpg").exists()

    # DB column must be NULL
    await session.refresh(master)
    assert master.avatar_uploaded_at is None


# ---------- delete with no prior upload (no-op) ----------


@pytest.mark.asyncio
async def test_delete_avatar_no_op_when_none(
    session: AsyncSession,
    api_client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "avatars_dir", str(tmp_path))
    await _make_master(session, tg_id=91005)
    _install_overrides(session, tg_id=91005)

    r = await api_client.delete("/v1/master/me/avatar")
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}


# ---------- unauthorized ----------


@pytest.mark.asyncio
async def test_upload_avatar_no_auth_header(
    session: AsyncSession,
    api_client: AsyncClient,
    tmp_path: Path,
) -> None:
    # No dependency_overrides installed → require_tg_user expects the header
    r = await api_client.post(
        "/v1/master/me/avatar",
        files={"file": ("avatar.png", _png(), "image/png")},
    )
    # FastAPI returns 422 (missing required header) or 401/503 (auth failure) —
    # in either case it must NOT be 200.
    assert r.status_code != 200
