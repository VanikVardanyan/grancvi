# Master Avatar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать мастеру загрузить фото профиля через бота. Аватар хранится локально на VPS как один JPEG 256×256 на мастера, отдаётся FastAPI `StaticFiles`'ом и попадает в публичные `PublicMasterOut` / `PublicSalonMasterOut` под ключом `avatar_url`.

**Architecture:** Pillow + pillow-heif (HEIC с iPhone) обрабатывают входящее фото — центральный square crop, ресайз до 256×256, JPEG q=85. Файл `<master_id>.jpg` пишется атомарно (`os.replace`) в каталог, монтируемый named volume `avatars_data` в оба контейнера (`api` читает, `app_bot` пишет). Колонка `Master.avatar_uploaded_at: datetime | None` служит индикатором «есть/нет» и cache-busting'ом через query-параметр `?v=<unix_ts>`. Загрузка идёт из бота: новый шаг `MasterRegister.waiting_avatar` в онбординге (с кнопкой «Пропустить») и кнопка «Аватар» в меню профиля с действиями «Заменить» / «Удалить».

**Tech Stack:** Python 3.12 async, aiogram 3.x, SQLAlchemy 2.0 async, Alembic, FastAPI, PostgreSQL 16, Pillow, pillow-heif, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-05-10-master-avatar-design.md`

---

## File Structure

**New files:**
- `src/services/avatars.py` — `AvatarService` + чистая функция `process_image(raw) -> bytes`.
- `src/handlers/master/avatar.py` — Router со всеми хендлерами аватара (онбординг + меню профиля).
- `tests/test_avatars_service.py` — unit тесты `process_image`, `save`, `delete`.
- `tests/test_masters_repo_avatar.py` — тесты `set_avatar_uploaded_at`.
- `tests/test_api_public_avatar.py` — API-тесты `avatar_url` в публичных эндпоинтах.
- `migrations/versions/<rev>_add_master_avatar_uploaded_at.py` — Alembic ревизия.

**Modified files:**
- `src/db/models.py` — добавить `avatar_uploaded_at` в `Master`.
- `src/repositories/masters.py` — метод `set_avatar_uploaded_at`.
- `src/exceptions.py` — `BadImage`, `AvatarTooLarge`.
- `src/config.py` — `avatars_dir: str` setting.
- `src/api/main.py` — `mkdir` + `StaticFiles` mount.
- `src/api/schemas.py` — `avatar_url` в `PublicMasterOut` и `PublicSalonMasterOut`.
- `src/api/routes/public.py` — `_avatar_url` хелпер, заполнение в обоих хендлерах.
- `src/callback_data/profile.py` — расширить `ProfileFieldCallback` значением `"avatar"`, добавить `AvatarActionCallback`.
- `src/fsm/master_register.py` — `waiting_avatar` state.
- `src/fsm/profile.py` — `waiting_avatar` state.
- `src/handlers/master/registration.py` — после `svc.register` идём в `MasterRegister.waiting_avatar`, а не в `state.clear() + REGISTER_DONE`.
- `src/handlers/master/profile.py` — кнопка `PROFILE_BTN_AVATAR` в `profile_menu_kb`.
- `src/handlers/master/__init__.py` — подключить avatar router.
- `src/strings.py` — новые ключи в `_RU` и `_HY`.
- `pyproject.toml` — `pillow`, `pillow-heif`.
- `docker-compose.yml`, `docker-compose.prod.yml` — named volume `avatars_data` + маппинг в `api` и `app_bot`.

---

## Task 1: Database migration — `Master.avatar_uploaded_at`

**Files:**
- Modify: `src/db/models.py` (Master class, after `onboarded_at`)
- Create: `migrations/versions/<rev>_add_master_avatar_uploaded_at.py`

- [ ] **Step 1: Add the column to the SQLAlchemy model**

Open `src/db/models.py` and add after `onboarded_at: Mapped[datetime | None] = mapped_column(...)` (around line 95):

```python
    avatar_uploaded_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
```

- [ ] **Step 2: Generate the Alembic migration**

Run from project root:

```bash
docker compose run --rm app_bot alembic revision --autogenerate -m "add_master_avatar_uploaded_at"
```

This produces a file `migrations/versions/<rev>_add_master_avatar_uploaded_at.py`. Open it and confirm the body contains exactly:

```python
def upgrade() -> None:
    op.add_column(
        "masters",
        sa.Column("avatar_uploaded_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("masters", "avatar_uploaded_at")
```

If alembic auto-generated extra unrelated changes (e.g. drift from server defaults), trim the file down to only the `add_column` / `drop_column` calls above. Keep the auto-generated `revision`, `down_revision`, and imports.

- [ ] **Step 3: Apply the migration**

```bash
docker compose run --rm app_bot alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade ... -> <rev>, add_master_avatar_uploaded_at`.

- [ ] **Step 4: Verify the column exists**

```bash
docker compose exec postgres psql -U botik -d botik -c "\d masters" | grep avatar
```

Expected output: `avatar_uploaded_at | timestamp with time zone |`

- [ ] **Step 5: Commit**

```bash
git add src/db/models.py migrations/versions/
git commit -m "feat(db): add Master.avatar_uploaded_at"
```

---

## Task 2: Repository method `set_avatar_uploaded_at` (TDD)

**Files:**
- Modify: `src/repositories/masters.py` (after `set_blocked`, end of class)
- Create: `tests/test_masters_repo_avatar.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_masters_repo_avatar.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.masters import MasterRepository


@pytest.mark.asyncio
async def test_set_avatar_uploaded_at_sets_and_clears(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    master = await repo.create(tg_id=12345, name="A")
    await session.flush()

    ts = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    await repo.set_avatar_uploaded_at(master.id, ts)
    await session.flush()
    refreshed = await repo.by_id(master.id)
    assert refreshed is not None
    assert refreshed.avatar_uploaded_at == ts

    await repo.set_avatar_uploaded_at(master.id, None)
    await session.flush()
    refreshed = await repo.by_id(master.id)
    assert refreshed is not None
    assert refreshed.avatar_uploaded_at is None
```

- [ ] **Step 2: Run the test — verify it fails**

```bash
docker compose run --rm app_bot pytest tests/test_masters_repo_avatar.py -v
```

Expected: FAIL with `AttributeError: 'MasterRepository' object has no attribute 'set_avatar_uploaded_at'`.

- [ ] **Step 3: Implement the method**

In `src/repositories/masters.py`, after `set_blocked` (the last method), add:

```python
    async def set_avatar_uploaded_at(self, master_id: Any, ts: "datetime | None") -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.avatar_uploaded_at = ts
```

`datetime` is already imported at line 3 (`from datetime import UTC`). Add `from datetime import datetime` to the same import line if it isn't there yet — check the file. If only `UTC` is imported, change to `from datetime import UTC, datetime`.

- [ ] **Step 4: Run the test — verify it passes**

```bash
docker compose run --rm app_bot pytest tests/test_masters_repo_avatar.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/repositories/masters.py tests/test_masters_repo_avatar.py
git commit -m "feat(repo): MasterRepository.set_avatar_uploaded_at"
```

---

## Task 3: Add Pillow + pillow-heif dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock` (regenerated)

- [ ] **Step 1: Add the deps to `pyproject.toml`**

In `pyproject.toml`, find the `dependencies = [ ... ]` block and add two lines (keep alphabetical-ish where reasonable, the existing order is mixed so just append after `posthog>=3.7`):

```toml
    "pillow>=10.3",
    "pillow-heif>=0.16",
```

- [ ] **Step 2: Lock deps and rebuild image**

```bash
uv lock
docker compose build app_bot api
```

Expected: build succeeds, no missing wheel errors.

- [ ] **Step 3: Smoke check that imports work in the container**

```bash
docker compose run --rm app_bot python -c "import PIL; from pillow_heif import register_heif_opener; register_heif_opener(); from PIL import Image; print(Image.MIME)"
```

Expected: dictionary printed without errors. If `pillow-heif` wheel is missing for the platform, the command will surface the error here.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add pillow + pillow-heif for master avatars"
```

---

## Task 4: Config — `avatars_dir` + custom exceptions

**Files:**
- Modify: `src/config.py`
- Modify: `src/exceptions.py`

- [ ] **Step 1: Add the setting**

In `src/config.py`, inside the `Settings` class, after `recaptcha_min_score: float = 0.5` (around line 79), add:

```python
    # Local filesystem directory for master avatar JPEGs. Mounted via the
    # avatars_data Docker volume in compose. Override in dev via env if you
    # want to point at a host path, e.g. AVATARS_DIR=/tmp/avatars.
    avatars_dir: str = "/app/data/avatars"
```

- [ ] **Step 2: Add the exceptions**

In `src/exceptions.py`, append at the end:

```python
class BadImage(Exception):
    """Raised when uploaded avatar bytes are not a valid image."""


class AvatarTooLarge(Exception):
    """Raised when uploaded avatar exceeds the size cap."""
```

- [ ] **Step 3: Quick import sanity**

```bash
docker compose run --rm app_bot python -c "from src.config import settings; from src.exceptions import BadImage, AvatarTooLarge; print(settings.avatars_dir)"
```

Expected: `/app/data/avatars`.

- [ ] **Step 4: Commit**

```bash
git add src/config.py src/exceptions.py
git commit -m "feat(config): avatars_dir setting + BadImage/AvatarTooLarge exceptions"
```

---

## Task 5: Docker compose — `avatars_data` volume

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml`

- [ ] **Step 1: Add the volume to dev compose**

In `docker-compose.yml`, find the `api` service and add `volumes` (sibling of `command`, `depends_on`, `env_file`, `ports`):

```yaml
  api:
    build: .
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000
    depends_on:
      postgres:
        condition: service_healthy
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://botik:botik@postgres:5432/botik
      REDIS_URL: redis://redis:6379/0
    ports:
      - "127.0.0.1:8000:8000"
    restart: unless-stopped
    volumes:
      - avatars_data:/app/data/avatars
```

Same volumes block under `app_bot`:

```yaml
  app_bot:
    build: .
    command: sh -c "alembic upgrade head && exec python -m src.app_bot_main"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://botik:botik@postgres:5432/botik
      REDIS_URL: redis://redis:6379/0
    restart: unless-stopped
    volumes:
      - avatars_data:/app/data/avatars
```

At the bottom of the file extend the `volumes:` block so it reads:

```yaml
volumes:
  pg_data:
  avatars_data:
```

- [ ] **Step 2: Add the volume to prod compose**

In `docker-compose.prod.yml`, the `api` and `app_bot` services already exist as overlays without `volumes`. Add `volumes: ["avatars_data:/app/data/avatars"]` to each:

```yaml
  api:
    restart: always
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/v1/health', timeout=3)"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 15s
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    volumes:
      - avatars_data:/app/data/avatars

  app_bot:
    restart: always
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    volumes:
      - avatars_data:/app/data/avatars
```

If `docker-compose.prod.yml` does not have a top-level `volumes:` block, add it at the bottom:

```yaml
volumes:
  avatars_data:
```

(If it already inherits from the dev file via `volumes: { pg_data: }`, the named volume from the dev file is reused — but make sure prod compose still has at least an empty entry for `avatars_data` so docker-compose doesn't barf on missing definition.)

- [ ] **Step 3: Recreate the dev `app_bot` and `api` to mount the volume**

```bash
docker compose up -d --force-recreate api app_bot
docker compose exec api ls -la /app/data
```

Expected: `/app/data/avatars` directory exists (or will be created on first write — that's fine; just confirm `/app/data` is writable). If `/app/data` does not exist yet because nothing wrote into it, the directory will be created on `mkdir(parents=True, exist_ok=True)` in Task 7. Skip this verification step in that case.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml docker-compose.prod.yml
git commit -m "chore(compose): add avatars_data named volume"
```

---

## Task 6: `AvatarService` — process_image, save, delete (TDD)

**Files:**
- Create: `src/services/avatars.py`
- Create: `tests/test_avatars_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_avatars_service.py`:

```python
from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from pillow_heif import register_heif_opener

from src.exceptions import BadImage
from src.services.avatars import AvatarService, process_image

register_heif_opener()


def _jpeg_bytes(width: int, height: int, color: tuple[int, int, int] = (10, 100, 200)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _png_bytes_with_alpha(size: int = 800) -> bytes:
    img = Image.new("RGBA", (size, size), (10, 100, 200, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _heic_bytes(size: int = 1200) -> bytes:
    img = Image.new("RGB", (size, size), (200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="HEIF", quality=80)
    return buf.getvalue()


def test_process_image_landscape_jpeg_to_256x256() -> None:
    raw = _jpeg_bytes(3000, 2000)
    out = process_image(raw)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.size == (256, 256)
    assert len(out) <= 60_000


def test_process_image_portrait_jpeg_to_256x256() -> None:
    raw = _jpeg_bytes(800, 1600)
    out = process_image(raw)
    img = Image.open(io.BytesIO(out))
    assert img.size == (256, 256)


def test_process_image_png_with_alpha_returns_jpeg() -> None:
    raw = _png_bytes_with_alpha()
    out = process_image(raw)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.size == (256, 256)
    assert img.mode == "RGB"


def test_process_image_heic_decodes() -> None:
    raw = _heic_bytes()
    out = process_image(raw)
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG"
    assert img.size == (256, 256)


def test_process_image_garbage_raises_bad_image() -> None:
    with pytest.raises(BadImage):
        process_image(b"definitely not an image")


def test_save_writes_file_atomically(tmp_path: Path) -> None:
    svc = AvatarService(directory=str(tmp_path))
    master_id = uuid4()
    svc.save(master_id, _jpeg_bytes(900, 900))
    target = tmp_path / f"{master_id}.jpg"
    assert target.exists()
    img = Image.open(target)
    assert img.size == (256, 256)


def test_save_overwrites_existing(tmp_path: Path) -> None:
    svc = AvatarService(directory=str(tmp_path))
    master_id = uuid4()
    svc.save(master_id, _jpeg_bytes(900, 900, color=(255, 0, 0)))
    first_size = (tmp_path / f"{master_id}.jpg").stat().st_size
    svc.save(master_id, _jpeg_bytes(900, 900, color=(0, 0, 255)))
    second_size = (tmp_path / f"{master_id}.jpg").stat().st_size
    # Different colors → different bytes; we only assert file still exists and is non-empty.
    assert second_size > 0
    assert first_size > 0


def test_delete_removes_file(tmp_path: Path) -> None:
    svc = AvatarService(directory=str(tmp_path))
    master_id = uuid4()
    svc.save(master_id, _jpeg_bytes(900, 900))
    svc.delete(master_id)
    assert not (tmp_path / f"{master_id}.jpg").exists()


def test_delete_missing_is_noop(tmp_path: Path) -> None:
    svc = AvatarService(directory=str(tmp_path))
    svc.delete(uuid4())  # should not raise


def test_path_for_returns_expected_filename(tmp_path: Path) -> None:
    svc = AvatarService(directory=str(tmp_path))
    master_id = uuid4()
    assert svc.path_for(master_id) == tmp_path / f"{master_id}.jpg"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
docker compose run --rm app_bot pytest tests/test_avatars_service.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.services.avatars'`.

- [ ] **Step 3: Implement `AvatarService`**

Create `src/services/avatars.py`:

```python
from __future__ import annotations

import io
import os
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from src.exceptions import BadImage

register_heif_opener()


_TARGET_SIZE = 256
_JPEG_QUALITY = 85


def process_image(raw: bytes) -> bytes:
    """Decode arbitrary image bytes, return a 256x256 JPEG.

    Steps: validate → EXIF orient → center-crop to square → resize → JPEG q=85.
    """
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise BadImage(str(exc)) from exc

    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        side = min(img.size)
        left = (img.size[0] - side) // 2
        top = (img.size[1] - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((_TARGET_SIZE, _TARGET_SIZE), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        return out.getvalue()
    except (OSError, ValueError) as exc:
        raise BadImage(str(exc)) from exc


class AvatarService:
    """Filesystem persistence for master avatars.

    One JPEG per master, named ``<master_id>.jpg`` under ``directory``.
    Writes are atomic: temp file in the same directory, then ``os.replace``.
    """

    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)

    def path_for(self, master_id: uuid.UUID) -> Path:
        return self._dir / f"{master_id}.jpg"

    def save(self, master_id: uuid.UUID, raw: bytes) -> None:
        processed = process_image(raw)
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self.path_for(master_id)
        tmp = target.with_suffix(".jpg.tmp")
        tmp.write_bytes(processed)
        os.replace(tmp, target)

    def delete(self, master_id: uuid.UUID) -> None:
        self.path_for(master_id).unlink(missing_ok=True)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
docker compose run --rm app_bot pytest tests/test_avatars_service.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/avatars.py tests/test_avatars_service.py
git commit -m "feat(services): AvatarService + process_image (HEIC supported)"
```

---

## Task 7: Public API — `avatar_url` field + `StaticFiles` mount (TDD)

**Files:**
- Modify: `src/api/schemas.py`
- Modify: `src/api/main.py`
- Modify: `src/api/routes/public.py`
- Create: `tests/test_api_public_avatar.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_api_public_avatar.py`:

```python
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

    async def _override() -> AsyncSession:  # type: ignore[override]
        async with session_maker() as s:
            yield s  # type: ignore[misc]

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

    async def _override() -> AsyncSession:  # type: ignore[override]
        async with session_maker() as s:
            yield s  # type: ignore[misc]

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
    salon = Salon(slug="my-salon", name="My Salon", is_public=True)
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

    async def _override() -> AsyncSession:  # type: ignore[override]
        async with session_maker() as s:
            yield s  # type: ignore[misc]

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
```

(If `Salon` is not at `src/db/models.py`'s top level — verify via `grep -n "class Salon" src/db/models.py` and adjust the import.)

- [ ] **Step 2: Run tests — verify they fail**

```bash
docker compose run --rm app_bot pytest tests/test_api_public_avatar.py -v
```

Expected: FAIL with KeyError or assertion errors on `avatar_url`.

- [ ] **Step 3: Add `avatar_url` to schemas**

In `src/api/schemas.py`, find class `PublicMasterOut` (around line 326) and add the field:

```python
class PublicMasterOut(BaseModel):
    id: UUID
    name: str
    slug: str
    specialty: str
    phone: str | None
    lang: str
    avatar_url: str | None = None
```

Then class `PublicSalonMasterOut` (around line 337):

```python
class PublicSalonMasterOut(BaseModel):
    slug: str
    name: str
    specialty: str
    avatar_url: str | None = None
```

(Preserve other existing fields exactly as they are; the diffs above show the full final shape — match the existing fields list and just append `avatar_url`.)

- [ ] **Step 4: Mount `StaticFiles` and create the directory**

In `src/api/main.py`, add imports at the top with the others:

```python
from pathlib import Path

from fastapi.staticfiles import StaticFiles
```

After `register_exception_handlers(app)` and before the first `app.include_router(...)`, add:

```python
Path(settings.avatars_dir).mkdir(parents=True, exist_ok=True)
app.mount(
    "/static/avatars",
    StaticFiles(directory=settings.avatars_dir),
    name="avatars",
)
```

- [ ] **Step 5: Add `_avatar_url` helper and use it in public routes**

In `src/api/routes/public.py`, near the top of the file (after imports, before the first route), add:

```python
def _avatar_url(master: Master) -> str | None:
    if master.avatar_uploaded_at is None:
        return None
    return f"/static/avatars/{master.id}.jpg?v={int(master.avatar_uploaded_at.timestamp())}"
```

Then update `public_master_by_slug` (around line 124). The existing return looks like:

```python
    return PublicMasterOut(
        id=master.id,
        name=master.name,
        slug=master.slug,
        specialty=await _resolve_specialty_text(session, master.specialty_text, lang),
        phone=master.phone if master.phone_public and master.phone else None,
        lang=master.lang,
    )
```

Add one line:

```python
    return PublicMasterOut(
        id=master.id,
        name=master.name,
        slug=master.slug,
        specialty=await _resolve_specialty_text(session, master.specialty_text, lang),
        phone=master.phone if master.phone_public and master.phone else None,
        lang=master.lang,
        avatar_url=_avatar_url(master),
    )
```

In `public_salon_by_slug` (around line 134) — the loop building `masters_out`. Existing:

```python
    for m in masters_rows:
        masters_out.append(
            PublicSalonMasterOut(
                slug=m.slug,
                name=m.name,
                specialty=await _resolve_specialty_text(session, m.specialty_text, lang),
            )
        )
```

Becomes:

```python
    for m in masters_rows:
        masters_out.append(
            PublicSalonMasterOut(
                slug=m.slug,
                name=m.name,
                specialty=await _resolve_specialty_text(session, m.specialty_text, lang),
                avatar_url=_avatar_url(m),
            )
        )
```

- [ ] **Step 6: Run tests — verify they pass**

```bash
docker compose run --rm app_bot pytest tests/test_api_public_avatar.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 7: Smoke check — full test suite still green**

```bash
docker compose run --rm app_bot pytest -q
```

Expected: no regressions.

- [ ] **Step 8: Commit**

```bash
git add src/api/schemas.py src/api/main.py src/api/routes/public.py tests/test_api_public_avatar.py
git commit -m "feat(api): expose avatar_url + mount /static/avatars"
```

---

## Task 8: FSM states + callback data

**Files:**
- Modify: `src/fsm/master_register.py`
- Modify: `src/fsm/profile.py`
- Modify: `src/callback_data/profile.py`

- [ ] **Step 1: Add `waiting_avatar` to `MasterRegister`**

Replace `src/fsm/master_register.py` with:

```python
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MasterRegister(StatesGroup):
    waiting_lang = State()
    waiting_name = State()
    waiting_phone = State()
    waiting_specialty = State()
    waiting_slug_confirm = State()
    waiting_custom_slug = State()
    waiting_avatar = State()
```

- [ ] **Step 2: Add `waiting_avatar` to `ProfileEdit`**

Replace `src/fsm/profile.py` with:

```python
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ProfileEdit(StatesGroup):
    menu = State()
    waiting_name = State()
    waiting_specialty = State()
    waiting_slug = State()
    waiting_avatar = State()
```

- [ ] **Step 3: Extend `ProfileFieldCallback` and add `AvatarActionCallback`**

Replace `src/callback_data/profile.py` with:

```python
from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class ProfileFieldCallback(CallbackData, prefix="pf"):
    field: Literal["name", "specialty", "slug", "avatar"]


class AvatarActionCallback(CallbackData, prefix="av"):
    action: Literal["replace", "delete", "back", "skip"]
```

- [ ] **Step 4: Sanity import**

```bash
docker compose run --rm app_bot python -c "from src.callback_data.profile import ProfileFieldCallback, AvatarActionCallback; from src.fsm.master_register import MasterRegister; from src.fsm.profile import ProfileEdit; print(ProfileFieldCallback(field='avatar').pack(), AvatarActionCallback(action='skip').pack())"
```

Expected: two non-empty callback strings printed.

- [ ] **Step 5: Commit**

```bash
git add src/fsm/master_register.py src/fsm/profile.py src/callback_data/profile.py
git commit -m "feat(fsm): waiting_avatar states + AvatarActionCallback"
```

---

## Task 9: i18n strings (RU + HY)

**Files:**
- Modify: `src/strings.py`

- [ ] **Step 1: Add new keys to `_RU`**

In `src/strings.py`, find the `_RU` dict. The `PROFILE_*` block is around line 326. Insert these new keys near the existing `PROFILE_BTN_SLUG` line (keep them grouped):

```python
    "PROFILE_BTN_AVATAR": "🖼 Аватар",
    "PROFILE_AVATAR_NONE": "Аватара пока нет. Пришлите фото — увидят клиенты на странице записи.",
    "PROFILE_AVATAR_PRESENT": "Текущий аватар. Можно заменить или удалить.",
    "PROFILE_AVATAR_REPLACE_BTN": "🔄 Заменить",
    "PROFILE_AVATAR_DELETE_BTN": "🗑 Удалить",
    "PROFILE_AVATAR_SEND_BTN": "📤 Прислать фото",
    "PROFILE_AVATAR_BACK_BTN": "⬅️ Назад",
    "REGISTER_ASK_AVATAR": "Пришлите фото профиля. Его увидят клиенты на странице записи. Можно пропустить — добавите потом из меню профиля.",
    "REGISTER_AVATAR_SKIP_BTN": "Пропустить",
    "AVATAR_TOO_LARGE": "Фото слишком большое — максимум 10 MB. Пришлите поменьше.",
    "AVATAR_BAD_IMAGE": "Не получилось прочитать картинку. Попробуйте другое фото.",
    "AVATAR_NEED_PHOTO": "Пришлите именно фото или картинку (не текст и не стикер).",
    "AVATAR_DELETED": "Аватар удалён.",
```

- [ ] **Step 2: Add new keys to `_HY` (mirror set, Armenian)**

Find the `_HY` dict (around line 393+) and the analogous `PROFILE_*` block. Add:

```python
    "PROFILE_BTN_AVATAR": "🖼 Ավատար",
    "PROFILE_AVATAR_NONE": "Ավատար դեռ չկա։ Ուղարկեք լուսանկար — հաճախորդները կտեսնեն այն գրանցման էջում։",
    "PROFILE_AVATAR_PRESENT": "Ընթացիկ ավատար։ Կարող եք փոխարինել կամ ջնջել։",
    "PROFILE_AVATAR_REPLACE_BTN": "🔄 Փոխարինել",
    "PROFILE_AVATAR_DELETE_BTN": "🗑 Ջնջել",
    "PROFILE_AVATAR_SEND_BTN": "📤 Ուղարկել լուսանկար",
    "PROFILE_AVATAR_BACK_BTN": "⬅️ Հետ",
    "REGISTER_ASK_AVATAR": "Ուղարկեք պրոֆիլի լուսանկար։ Հաճախորդները կտեսնեն այն գրանցման էջում։ Կարող եք բաց թողնել — հետո ավելացնեք պրոֆիլի մենյուից։",
    "REGISTER_AVATAR_SKIP_BTN": "Բաց թողնել",
    "AVATAR_TOO_LARGE": "Լուսանկարը չափազանց մեծ է — առավելագույնը 10 ՄԲ։ Ուղարկեք ավելի փոքրը։",
    "AVATAR_BAD_IMAGE": "Չստացվեց կարդալ նկարը։ Փորձեք այլ լուսանկար։",
    "AVATAR_NEED_PHOTO": "Ուղարկեք հենց լուսանկար կամ պատկեր (ոչ տեքստ կամ ստիկեր)։",
    "AVATAR_DELETED": "Ավատարը ջնջված է։",
```

- [ ] **Step 3: Sanity check that all keys resolve**

```bash
docker compose run --rm app_bot python -c "
from src.strings import set_current_lang, strings
for lang in ('ru', 'hy'):
    set_current_lang(lang)
    for key in (
        'PROFILE_BTN_AVATAR', 'PROFILE_AVATAR_NONE', 'PROFILE_AVATAR_PRESENT',
        'PROFILE_AVATAR_REPLACE_BTN', 'PROFILE_AVATAR_DELETE_BTN',
        'PROFILE_AVATAR_SEND_BTN', 'PROFILE_AVATAR_BACK_BTN',
        'REGISTER_ASK_AVATAR', 'REGISTER_AVATAR_SKIP_BTN',
        'AVATAR_TOO_LARGE', 'AVATAR_BAD_IMAGE', 'AVATAR_NEED_PHOTO', 'AVATAR_DELETED',
    ):
        assert getattr(strings, key), f'{lang}/{key} empty'
print('OK')
"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add src/strings.py
git commit -m "feat(i18n): RU+HY strings for master avatar"
```

---

## Task 10: Avatar handlers — onboarding + profile menu (new router)

**Files:**
- Create: `src/handlers/master/avatar.py`
- Modify: `src/handlers/master/__init__.py`

- [ ] **Step 1: Create the avatar router**

Create `src/handlers/master/avatar.py`:

```python
from __future__ import annotations

import io

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.profile import AvatarActionCallback, ProfileFieldCallback
from src.config import settings
from src.db.models import Master
from src.exceptions import BadImage
from src.fsm.master_register import MasterRegister
from src.fsm.profile import ProfileEdit
from src.keyboards.common import main_menu
from src.repositories.masters import MasterRepository
from src.services.avatars import AvatarService
from src.strings import strings
from src.utils.time import now_utc

router = Router(name="master_avatar")


_MAX_AVATAR_BYTES = 10 * 1024 * 1024


def _avatar_service() -> AvatarService:
    return AvatarService(directory=settings.avatars_dir)


def _onboarding_skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.REGISTER_AVATAR_SKIP_BTN,
                    callback_data=AvatarActionCallback(action="skip").pack(),
                )
            ]
        ]
    )


def _profile_avatar_present_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_AVATAR_REPLACE_BTN,
                    callback_data=AvatarActionCallback(action="replace").pack(),
                ),
                InlineKeyboardButton(
                    text=strings.PROFILE_AVATAR_DELETE_BTN,
                    callback_data=AvatarActionCallback(action="delete").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_AVATAR_BACK_BTN,
                    callback_data=AvatarActionCallback(action="back").pack(),
                )
            ],
        ]
    )


def _profile_avatar_absent_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_AVATAR_SEND_BTN,
                    callback_data=AvatarActionCallback(action="replace").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_AVATAR_BACK_BTN,
                    callback_data=AvatarActionCallback(action="back").pack(),
                )
            ],
        ]
    )


async def _download_photo_bytes(message: Message) -> bytes | None:
    """Pull the largest photo or an image document. Returns None if oversize."""
    if message.bot is None:
        return None
    if message.photo:
        photo = message.photo[-1]
        if photo.file_size and photo.file_size > _MAX_AVATAR_BYTES:
            return None
        buf = io.BytesIO()
        await message.bot.download(photo, destination=buf)
        return buf.getvalue()
    if message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        doc = message.document
        if doc.file_size and doc.file_size > _MAX_AVATAR_BYTES:
            return None
        buf = io.BytesIO()
        await message.bot.download(doc, destination=buf)
        return buf.getvalue()
    return None


async def _persist_avatar(
    *,
    raw: bytes,
    master: Master,
    session: AsyncSession,
) -> None:
    _avatar_service().save(master.id, raw)
    await MasterRepository(session).set_avatar_uploaded_at(master.id, now_utc())
    await session.commit()


@router.message(MasterRegister.waiting_avatar, F.photo | F.document)
async def onboarding_avatar_received(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    raw = await _download_photo_bytes(message)
    if raw is None:
        if message.document and not (message.document.mime_type or "").startswith("image/"):
            await message.answer(strings.AVATAR_NEED_PHOTO)
            return
        await message.answer(strings.AVATAR_TOO_LARGE)
        return
    try:
        await _persist_avatar(raw=raw, master=master, session=session)
    except BadImage:
        await message.answer(strings.AVATAR_BAD_IMAGE)
        return
    await state.clear()
    await message.answer(strings.REGISTER_DONE, reply_markup=main_menu())


@router.message(MasterRegister.waiting_avatar)
async def onboarding_avatar_other(message: Message) -> None:
    await message.answer(strings.AVATAR_NEED_PHOTO)


@router.callback_query(
    MasterRegister.waiting_avatar,
    AvatarActionCallback.filter(F.action == "skip"),
)
async def onboarding_avatar_skip(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if cb.message is not None:
        await cb.message.answer(strings.REGISTER_DONE, reply_markup=main_menu())
    await cb.answer()


@router.callback_query(ProfileFieldCallback.filter(F.field == "avatar"))
async def profile_avatar_open(
    cb: CallbackQuery,
    state: FSMContext,
    master: Master,
) -> None:
    await state.set_state(ProfileEdit.menu)
    if cb.message is None:
        await cb.answer()
        return
    if master.avatar_uploaded_at is not None:
        path = _avatar_service().path_for(master.id)
        if path.exists():
            await cb.message.answer_photo(
                photo=FSInputFile(str(path)),
                caption=strings.PROFILE_AVATAR_PRESENT,
                reply_markup=_profile_avatar_present_kb(),
            )
            await cb.answer()
            return
    await cb.message.answer(
        strings.PROFILE_AVATAR_NONE,
        reply_markup=_profile_avatar_absent_kb(),
    )
    await cb.answer()


@router.callback_query(AvatarActionCallback.filter(F.action == "replace"))
async def profile_avatar_replace(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileEdit.waiting_avatar)
    if cb.message is not None:
        await cb.message.answer(strings.REGISTER_ASK_AVATAR)
    await cb.answer()


@router.callback_query(AvatarActionCallback.filter(F.action == "delete"))
async def profile_avatar_delete(
    cb: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    _avatar_service().delete(master.id)
    await MasterRepository(session).set_avatar_uploaded_at(master.id, None)
    await session.commit()
    await state.clear()
    if cb.message is not None:
        await cb.message.answer(strings.AVATAR_DELETED)
    await cb.answer()


@router.callback_query(AvatarActionCallback.filter(F.action == "back"))
async def profile_avatar_back(cb: CallbackQuery, state: FSMContext) -> None:
    from src.handlers.master.profile import profile_menu_kb

    await state.set_state(ProfileEdit.menu)
    if cb.message is not None:
        await cb.message.answer(strings.PROFILE_MENU_TITLE, reply_markup=profile_menu_kb())
    await cb.answer()


@router.message(ProfileEdit.waiting_avatar, F.photo | F.document)
async def profile_avatar_received(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    raw = await _download_photo_bytes(message)
    if raw is None:
        if message.document and not (message.document.mime_type or "").startswith("image/"):
            await message.answer(strings.AVATAR_NEED_PHOTO)
            return
        await message.answer(strings.AVATAR_TOO_LARGE)
        return
    try:
        await _persist_avatar(raw=raw, master=master, session=session)
    except BadImage:
        await message.answer(strings.AVATAR_BAD_IMAGE)
        return
    await state.clear()
    await message.answer(strings.PROFILE_UPDATED)


@router.message(ProfileEdit.waiting_avatar)
async def profile_avatar_other(message: Message) -> None:
    await message.answer(strings.AVATAR_NEED_PHOTO)
```

NOTE on `now_utc`: verify the helper exists at `src/utils/time.py` (per CLAUDE.md). If not — replace `from src.utils.time import now_utc` with `from datetime import UTC, datetime` and `now_utc()` calls with `datetime.now(UTC)`.

NOTE on `master: Master` fixture: this is the existing aiogram middleware injection used by other master handlers (see `src/handlers/master/profile.py`). It is provided by `src/middlewares/...`. Do not redefine.

- [ ] **Step 2: Register the router**

In `src/handlers/master/__init__.py`, add the import and `include_router` line:

```python
from src.handlers.master.avatar import router as avatar_router
```

```python
router.include_router(avatar_router)
```

Place the `include_router(avatar_router)` after `include_router(profile_router)` (last line currently).

- [ ] **Step 3: Sanity import**

```bash
docker compose run --rm app_bot python -c "from src.handlers.master import router; print('handlers ok')"
```

Expected: `handlers ok`.

- [ ] **Step 4: Run full test suite**

```bash
docker compose run --rm app_bot pytest -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/handlers/master/avatar.py src/handlers/master/__init__.py
git commit -m "feat(bot): avatar router — onboarding step + profile menu"
```

---

## Task 11: Wire avatar step into onboarding finalize

**Files:**
- Modify: `src/handlers/master/registration.py`

- [ ] **Step 1: Replace the post-register branch in `_finalize`**

In `src/handlers/master/registration.py`, find `_finalize` (around line 140). The bottom of the function currently looks like:

```python
    await state.clear()
    if out_message is not None:
        await out_message.answer(strings.REGISTER_DONE, reply_markup=main_menu())
```

Replace with:

```python
    if out_message is not None:
        await state.set_state(MasterRegister.waiting_avatar)
        await out_message.answer(
            strings.REGISTER_ASK_AVATAR,
            reply_markup=_onboarding_skip_kb_local(),
        )
    else:
        await state.clear()
```

Add a small helper at module level (near the top, after the existing `_HINT_MAP`) so `registration.py` doesn't have to import from `avatar.py` and create a circular dependency:

```python
def _onboarding_skip_kb_local():
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.callback_data.profile import AvatarActionCallback

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.REGISTER_AVATAR_SKIP_BTN,
                    callback_data=AvatarActionCallback(action="skip").pack(),
                )
            ]
        ]
    )
```

(The avatar router contains the same keyboard for its own use; duplicating one tiny function avoids cross-module imports between `registration` and `avatar`.)

- [ ] **Step 2: Run tests**

```bash
docker compose run --rm app_bot pytest -q
```

Expected: all tests still pass. If existing onboarding tests assert `REGISTER_DONE` immediately after registering, they will now see `REGISTER_ASK_AVATAR`. Update those tests by either:
- amending them to drive past the avatar step with a skip callback, OR
- updating the assertion to `REGISTER_ASK_AVATAR`.

Pick whichever is closer to the existing test's intent. Run again until green.

- [ ] **Step 3: Commit**

```bash
git add src/handlers/master/registration.py tests/
git commit -m "feat(bot): onboarding asks for avatar before main menu"
```

---

## Task 12: Add «Аватар» button to profile menu

**Files:**
- Modify: `src/handlers/master/profile.py`

- [ ] **Step 1: Extend `profile_menu_kb`**

In `src/handlers/master/profile.py`, find `profile_menu_kb` (around line 24). It currently has three rows: name / specialty / slug. Add a fourth row for avatar:

```python
def profile_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_BTN_NAME,
                    callback_data=ProfileFieldCallback(field="name").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_BTN_SPECIALTY,
                    callback_data=ProfileFieldCallback(field="specialty").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_BTN_SLUG,
                    callback_data=ProfileFieldCallback(field="slug").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_BTN_AVATAR,
                    callback_data=ProfileFieldCallback(field="avatar").pack(),
                )
            ],
        ]
    )
```

- [ ] **Step 2: Run tests**

```bash
docker compose run --rm app_bot pytest -q
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
git add src/handlers/master/profile.py
git commit -m "feat(bot): add Avatar button to profile menu"
```

---

## Task 13: Manual smoke test — end-to-end

**Goal:** Verify the full flow from a real Telegram client and the public API. No code, just manual checks.

- [ ] **Step 1: Rebuild and restart**

```bash
docker compose up -d --build api app_bot
docker compose ps
```

Expected: both services `Up` and healthy.

- [ ] **Step 2: Onboarding flow**

In Telegram, register a fresh test master (use a spare account or test invite). Walk through `lang → name → phone → specialty → slug`. After confirming the slug, the bot must ask: `Пришлите фото профиля. ...` with a `Пропустить` button.

- Send a normal photo via the photo button → bot should answer `Готово! Профиль создан. ...` and show the main menu. The container should produce `<master_id>.jpg` under the volume:
  ```bash
  docker compose exec api ls -la /app/data/avatars
  ```
- Repeat with another test master and tap `Пропустить` → no file created, main menu shown.
- Repeat with a third test master and send a >10 MB image (use a high-res HEIC from iPhone if needed — or `dd if=/dev/urandom of=big.jpg bs=1M count=12` and send that as document) → bot answers `Фото слишком большое — максимум 10 MB.`
- Repeat with the same master and send a HEIC photo (iPhone camera roll, choose «File» path or via «Photo» — both should work) → 256×256 JPEG saved.

- [ ] **Step 3: Profile menu flow**

For an existing master, `/start` → settings → `Мой профиль` → tap `🖼 Аватар`.
- If no avatar yet: bot replies with text + `Прислать фото` / `Назад`. Tap `Прислать фото`, send a photo → `Готово ✅`.
- Now `Мой профиль` → `Аватар`: bot replies with the existing photo + `Заменить` / `Удалить` / `Назад`.
- Tap `Заменить`, send a different photo → `Готово ✅`. Repeat the menu — new photo shown.
- Tap `Удалить` → `Аватар удалён.` File gone:
  ```bash
  docker compose exec api ls -la /app/data/avatars
  ```

- [ ] **Step 4: Public API check**

```bash
SLUG=<test-master-slug>
curl -s "http://127.0.0.1:8000/v1/public/masters/${SLUG}" | jq '.avatar_url'
```

Expected: a URL like `/static/avatars/<uuid>.jpg?v=<unix-ts>` after upload, `null` after delete.

```bash
curl -sI "http://127.0.0.1:8000/static/avatars/<uuid>.jpg" | head -5
```

Expected: `HTTP/1.1 200 OK` with `last-modified` and `content-type: image/jpeg`.

If the master is in a salon, also:
```bash
SALON=<salon-slug>
curl -s "http://127.0.0.1:8000/v1/public/salons/${SALON}" | jq '.masters[].avatar_url'
```

Expected: the test master's URL appears in the list.

- [ ] **Step 5: Update CHANGELOG (optional but consistent with the repo)**

If `CHANGELOG.md` is actively maintained (check `git log -p CHANGELOG.md | head -40`), add a one-liner under the next pending release section. Otherwise skip.

- [ ] **Step 6: Final commit (only if smoke test produced changes — usually skipped)**

If the smoke test surfaced no bugs, no commit here. If it surfaced bugs, fix them in their respective tasks (don't pile fixes into a single commit).

---

## Self-review checklist (run before handing off)

- [x] Spec coverage: storage, image processing, API, bot UX, files list, i18n, migration, tests, risks — all covered.
- [x] No placeholders, no "TODO" / "TBD" / "implement later".
- [x] Type/method consistency: `set_avatar_uploaded_at`, `process_image`, `AvatarService.save/delete/path_for`, `_avatar_url`, `AvatarActionCallback`, `ProfileFieldCallback(field="avatar")` used consistently throughout.
- [x] Tests precede implementation in TDD tasks.
- [x] Each task ends with a commit step.
