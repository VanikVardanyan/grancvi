# Public Web Booking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Allow clients to book a master directly on `grancvi.am/<slug>` without Telegram — picking service/date/time/contacts in a 3-step wizard. Master receives notifications via existing Telegram flow.

**Architecture:** New unauthenticated public endpoints in FastAPI (rate-limited via Redis, optional reCAPTCHA). Lander page (`r.html`) detects whether opened in Telegram client — if yes redirects to TMA as today, if no renders a booking wizard wired to the new endpoints. Bookings carry `source="web"`; existing `_approve_kb` master-notification flow is re-used unchanged. Optional Telegram opt-in via post-booking `link_<token>` deep-link binds `Client.tg_id` and surfaces the booking in the existing TMA `MyBookings` page.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Redis / pytest; vanilla JS + Tailwind on the lander; React in TMA.

**Spec:** `docs/superpowers/specs/2026-05-01-public-web-booking-design.md`
**UI mockup (approved):** `https://grancvi.am/book-mockup.html` (source in `grancvi-landing/book-mockup.html`)

---

## File Structure

### Backend (`tg-bot`, branch `feat/public-booking`)

| Файл | Действие | Ответственность |
|---|---|---|
| `src/db/models.py` | Modify | `Client.link_token: str \| None` (nullable, indexed) |
| `migrations/versions/0018_client_link_token.py` | Create | ALTER TABLE clients ADD COLUMN link_token + index |
| `src/api/schemas.py` | Modify | New schemas: `PublicMasterOut`, `PublicServiceOut`, `PublicSlotsOut`, `PublicBookingIn`, `PublicBookingOut`, `PublicBookingStatusOut` |
| `src/api/routes/public.py` | Modify | 5 new endpoints (services / slots-month / slots-day / create / status) |
| `src/services/booking.py` | Modify | `create_pending` accepts `source` parameter (default `"client_request"`); web path passes `"web"` |
| `src/utils/recaptcha.py` | Create | `verify_recaptcha(token, action) -> bool` — Google reCAPTCHA v3 verify; no-op if keys not configured |
| `src/utils/ratelimit.py` | Create | `consume_token(key, limit, window_sec) -> bool` — Redis sliding window |
| `src/config.py` | Modify | Add `recaptcha_site_key`, `recaptcha_secret`, `recaptcha_min_score`, `redis_url` (already exists) |
| `src/app_bot/handlers.py` | Modify | `_kind_for(start_param)` recognizes `link_<token>`; bot looks up `Client.link_token`, sets `tg_id`, clears token |
| `tests/test_api_public_bookings.py` | Create | Smoke tests for the new endpoints (read + create + status) |
| `tests/test_app_bot_handlers.py` | Modify | Test for `link_<token>` deep-link handler |

### Frontend lander (`grancvi-landing`, branch `master`)

| Файл | Действие | Ответственность |
|---|---|---|
| `r.html` | Modify | At top: detect Telegram client. If yes → existing redirect-to-TMA. Else → render booking wizard (same UI as `book-mockup.html`) wired to real API |
| `book-mockup.html` | Keep | Static UI demo, stays for reference; production path is `r.html` |

### Frontend TMA (`grancvi-web`, branch `feat/onboarding-redesign`)

| Файл | Действие |
|---|---|
| `src/App.tsx` | Modify — `RoleRouter` recognizes `start_param=link_<token>` and navigates to `/me` (booking shows up automatically because `Client.tg_id` was just linked by the bot) |

---

## Phase 1 — Backend

### Task 1: Branch + baseline

- [ ] **Step 1: Switch repo, create branch from main**

```bash
cd /Users/vanik/Desktop/projects/working-projects/tg-bot
git checkout main && git pull
git checkout -b feat/public-booking
docker compose up -d postgres redis
```

- [ ] **Step 2: Run baseline tests**

```bash
SENTRY_DSN= uv run pytest --tb=no -q | tail -3
```

Expected: 565+ passed.

---

### Task 2: Add `Client.link_token` migration

**Files:**
- Modify: `src/db/models.py` (find `class Client`)
- Create: `migrations/versions/0018_client_link_token.py`

- [ ] **Step 1: Add field to model**

Find `class Client(Base):` in `src/db/models.py` (around line 132). Add after the `phone` field:

```python
    # Token issued on web-booking when phone has no associated tg_id yet.
    # Bot's /start link_<token> handler binds Client.tg_id and clears
    # this field. Nullable so existing clients without web-flow stay clean.
    link_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
```

- [ ] **Step 2: Create migration**

Path: `migrations/versions/0018_client_link_token.py`

```python
"""client.link_token — one-shot token for binding tg_id from web booking

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-01 12:00:00.000000

Web-booking flow gives the new client a `link_<token>` deep-link to
the bot. When they tap, the bot resolves the token, sets Client.tg_id
to update.from_user.id, and clears the token so it's not reusable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("link_token", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_clients_link_token",
        "clients",
        ["link_token"],
        unique=False,
        postgresql_where=sa.text("link_token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_clients_link_token", table_name="clients")
    op.drop_column("clients", "link_token")
```

- [ ] **Step 3: Apply migration locally**

```bash
docker compose exec -T postgres psql -U botik -d botik -c "DROP DATABASE IF EXISTS botik_test;"
docker compose exec -T postgres psql -U botik -d botik -c "CREATE DATABASE botik_test;"
SENTRY_DSN= uv run alembic upgrade head
```

Expected: ends at `0018`.

- [ ] **Step 4: Run baseline tests — confirm migrations work in test setup**

```bash
SENTRY_DSN= uv run pytest tests/test_services_master_registration.py --tb=no -q
```

Expected: PASS.

- [ ] **Step 5: Lint + types**

```bash
uv run ruff check src/db/models.py migrations/versions/0018_client_link_token.py
uv run ruff format src/db/models.py migrations/versions/0018_client_link_token.py
uv run mypy src/db/models.py
```

Clean.

- [ ] **Step 6: Commit**

```bash
git add src/db/models.py migrations/versions/0018_client_link_token.py
git commit -m "feat(clients): add link_token column for web-to-Telegram opt-in"
```

---

### Task 3: Add config + utility helpers (rate-limit + reCAPTCHA)

**Files:**
- Modify: `src/config.py`
- Create: `src/utils/ratelimit.py`
- Create: `src/utils/recaptcha.py`
- Test: `tests/test_utils_ratelimit.py`

- [ ] **Step 1: Extend `src/config.py`**

Find the `Settings` class. Add fields:

```python
    # reCAPTCHA v3 — public bookings spam protection. When secret is empty,
    # the verify helper is a no-op (dev / test). Production: site key in
    # the lander HTML, secret here.
    recaptcha_site_key: str = ""
    recaptcha_secret: str = ""
    # Below this score the request is rejected. v3 returns 0..1, lower
    # means more bot-like. 0.5 is Google's recommended default.
    recaptcha_min_score: float = 0.5
```

Place near other `*_token` settings (alphabetical-ish if the file uses ordering).

- [ ] **Step 2: Create rate-limit helper**

Path: `src/utils/ratelimit.py`

```python
"""Simple per-key sliding-window rate-limit using Redis sorted sets.

`consume_token(key, limit, window_sec)` returns True if the request
fits in the window, False otherwise. Each call records `now` in the
sorted set; the oldest entries outside the window are pruned.

Designed for low-volume endpoints (public bookings) where a 1-2 ms
extra Redis round-trip is fine. Don't use for hot-path RPS.
"""

from __future__ import annotations

import time

from redis.asyncio import Redis


async def consume_token(
    redis: Redis,
    key: str,
    *,
    limit: int,
    window_sec: int,
) -> bool:
    """Return True if request is allowed, False if over the limit.

    Sliding window: counts requests in the trailing `window_sec` seconds.
    Records the current request before counting so concurrent calls
    don't slip through.
    """
    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - window_sec * 1000

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, cutoff_ms)
    pipe.zadd(key, {str(now_ms): now_ms})
    pipe.zcard(key)
    pipe.expire(key, window_sec)
    _, _, count, _ = await pipe.execute()

    return int(count) <= limit
```

- [ ] **Step 3: Create reCAPTCHA helper**

Path: `src/utils/recaptcha.py`

```python
"""Google reCAPTCHA v3 server-side verify.

Stub when `recaptcha_secret` is empty — returns True so dev/test
flows aren't gated on Google credentials. Production: configure the
secret in `.env`.
"""

from __future__ import annotations

import structlog
from httpx import AsyncClient, HTTPError

from src.config import settings

log: structlog.stdlib.BoundLogger = structlog.get_logger()

_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


async def verify_recaptcha(token: str | None, expected_action: str) -> bool:
    """Verify a v3 token against Google. Returns True on success.

    No-op (returns True) when `recaptcha_secret` is unset — keeps dev
    happy. Logs every reject in production for diagnostics.
    """
    if not settings.recaptcha_secret:
        return True
    if not token:
        log.warning("recaptcha_no_token", action=expected_action)
        return False
    try:
        async with AsyncClient(timeout=5.0) as client:
            r = await client.post(
                _VERIFY_URL,
                data={"secret": settings.recaptcha_secret, "response": token},
            )
            r.raise_for_status()
            data = r.json()
    except HTTPError as exc:
        log.warning("recaptcha_http_error", err=repr(exc))
        return False

    if not data.get("success"):
        log.warning("recaptcha_failure", errors=data.get("error-codes"))
        return False
    if expected_action and data.get("action") != expected_action:
        log.warning("recaptcha_action_mismatch", got=data.get("action"), expected=expected_action)
        return False
    score = float(data.get("score", 0.0))
    if score < settings.recaptcha_min_score:
        log.warning("recaptcha_low_score", score=score, action=expected_action)
        return False
    return True
```

- [ ] **Step 4: Write a smoke test for rate-limit**

Path: `tests/test_utils_ratelimit.py`

```python
"""Sanity tests for the sliding-window rate-limit helper."""

from __future__ import annotations

import asyncio

import pytest
from redis.asyncio import Redis

from src.utils.ratelimit import consume_token


@pytest.mark.asyncio
async def test_consume_token_allows_under_limit() -> None:
    r = Redis.from_url("redis://localhost:6379/9", decode_responses=False)
    await r.delete("test:rl:under")
    for _ in range(3):
        assert await consume_token(r, "test:rl:under", limit=5, window_sec=10) is True
    await r.aclose()


@pytest.mark.asyncio
async def test_consume_token_blocks_over_limit() -> None:
    r = Redis.from_url("redis://localhost:6379/9", decode_responses=False)
    await r.delete("test:rl:over")
    for _ in range(3):
        assert await consume_token(r, "test:rl:over", limit=3, window_sec=10) is True
    # 4th request — over the limit
    assert await consume_token(r, "test:rl:over", limit=3, window_sec=10) is False
    await r.aclose()


@pytest.mark.asyncio
async def test_consume_token_window_resets() -> None:
    r = Redis.from_url("redis://localhost:6379/9", decode_responses=False)
    await r.delete("test:rl:reset")
    assert await consume_token(r, "test:rl:reset", limit=1, window_sec=1) is True
    assert await consume_token(r, "test:rl:reset", limit=1, window_sec=1) is False
    # Wait past window
    await asyncio.sleep(1.2)
    assert await consume_token(r, "test:rl:reset", limit=1, window_sec=1) is True
    await r.aclose()
```

- [ ] **Step 5: Run rate-limit tests**

```bash
SENTRY_DSN= uv run pytest tests/test_utils_ratelimit.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Lint + types**

```bash
uv run ruff check src/utils/ratelimit.py src/utils/recaptcha.py src/config.py tests/test_utils_ratelimit.py
uv run ruff format src/utils/ratelimit.py src/utils/recaptcha.py src/config.py tests/test_utils_ratelimit.py
uv run mypy src/utils/ratelimit.py src/utils/recaptcha.py src/config.py
```

Clean.

- [ ] **Step 7: Commit**

```bash
git add src/utils/ratelimit.py src/utils/recaptcha.py src/config.py tests/test_utils_ratelimit.py
git commit -m "feat(utils): redis sliding-window rate-limit + reCAPTCHA v3 verify helper"
```

---

### Task 4: Public schemas + read endpoints

**Files:**
- Modify: `src/api/schemas.py`
- Modify: `src/api/routes/public.py`
- Test: `tests/test_api_public_bookings.py` (create)

- [ ] **Step 1: Add new schemas to `src/api/schemas.py`**

Find a sensible location (near other public-facing schemas). Add:

```python
class PublicMasterOut(BaseModel):
    """Master profile for the public web-booking page.

    Subset of MasterOut: drops fields the public page doesn't need
    (timezone, redirects). Phone shown only when phone_public is True.
    """
    id: UUID
    name: str
    slug: str
    specialty: str | None = None
    phone: str | None = None
    lang: str


class PublicServiceOut(BaseModel):
    """Active service of a master, public view."""
    id: UUID
    name: str
    duration_min: int
    price_amd: int | None = None


class PublicSlotOut(BaseModel):
    """A single bookable slot (start_at_utc)."""
    start_at_utc: datetime


class PublicMonthDayOut(BaseModel):
    """One day in a month, with availability flag."""
    date: str  # YYYY-MM-DD in master's local tz
    has_capacity: bool


class PublicMonthSlotsOut(BaseModel):
    """Month-view: which days have any free slot."""
    days: list[PublicMonthDayOut]


class PublicBookingIn(BaseModel):
    """Public booking creation payload."""
    master_slug: str = Field(..., min_length=1, max_length=64)
    service_id: UUID
    start_at_utc: datetime
    client_name: str = Field(..., min_length=1, max_length=200)
    client_phone: str = Field(..., min_length=8, max_length=20)
    recaptcha_token: str | None = None


class PublicBookingOut(BaseModel):
    """Returned to the lander after a successful POST."""
    id: UUID
    master_name: str
    service_name: str
    start_at: datetime  # in master's local tz
    status: str
    telegram_link_url: str  # https://t.me/<bot>?start=link_<token>


class PublicBookingStatusOut(BaseModel):
    """Returned from GET /v1/public/bookings/{id} — for status refresh."""
    id: UUID
    status: str
    master_name: str
    service_name: str
    start_at: datetime
```

If `from datetime import datetime` and `from uuid import UUID` aren't already imported at the top of `schemas.py`, ensure they are.

- [ ] **Step 2: Create test file with 3 failing tests for read endpoints**

Path: `tests/test_api_public_bookings.py`

```python
"""Public web-booking API — read + write smoke tests.

Endpoints tested:
- GET  /v1/public/masters/{slug}                  → master profile
- GET  /v1/public/masters/{slug}/services         → active services
- GET  /v1/public/masters/{slug}/slots/month      → days with capacity
- GET  /v1/public/masters/{slug}/slots/day        → free slots of a day
- POST /v1/public/bookings                        → create
- GET  /v1/public/bookings/{id}                   → status
"""

from __future__ import annotations

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from src.api.main import app
from src.db.models import Master, Service


@pytest.mark.asyncio
async def test_public_get_master_returns_profile(session) -> None:
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/v1/public/masters/public-anna")
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["name"] == "Public Anna"
    assert body["slug"] == "public-anna"
    assert body["lang"] == "hy"


@pytest.mark.asyncio
async def test_public_get_master_404_when_blocked(session) -> None:
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/v1/public/masters/blocked-anna")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_public_list_services_returns_active(session) -> None:
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/v1/public/masters/svc-anna/services")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["name"] == "Active"
```

- [ ] **Step 3: Run the new tests, confirm they fail (endpoints don't exist yet)**

```bash
SENTRY_DSN= uv run pytest tests/test_api_public_bookings.py -v
```

Expected: all 3 fail (404 for unknown route).

- [ ] **Step 4: Implement read endpoints in `src/api/routes/public.py`**

Look at the file's existing structure first. Then add the 4 read endpoints. Below the existing route definitions, add:

```python
from datetime import date as date_type

from fastapi import Query

from src.api.schemas import (
    PublicMasterOut,
    PublicMonthDayOut,
    PublicMonthSlotsOut,
    PublicServiceOut,
    PublicSlotOut,
)
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.services.availability import AvailabilityService


def _master_is_available(master: Master) -> bool:
    return master.is_public is True and master.blocked_at is None


@router.get("/masters/{slug}", response_model=PublicMasterOut)
async def public_master_by_slug(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> PublicMasterOut:
    master = await MasterRepository(session).by_slug(slug)
    if master is None or not _master_is_available(master):
        raise ApiError("not_found", "master not found", status_code=404)
    return PublicMasterOut(
        id=master.id,
        name=master.name,
        slug=master.slug,
        specialty=master.specialty_text or None,
        phone=master.phone if master.phone_public and master.phone else None,
        lang=master.lang,
    )


@router.get("/masters/{slug}/services", response_model=list[PublicServiceOut])
async def public_master_services(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> list[PublicServiceOut]:
    master = await MasterRepository(session).by_slug(slug)
    if master is None or not _master_is_available(master):
        raise ApiError("not_found", "master not found", status_code=404)
    services = await ServiceRepository(session).list_active(master.id)
    return [
        PublicServiceOut(
            id=s.id, name=s.name, duration_min=s.duration_min, price_amd=s.price_amd
        )
        for s in services
    ]


@router.get("/masters/{slug}/slots/month", response_model=PublicMonthSlotsOut)
async def public_master_slots_month(
    slug: str,
    service_id: UUID,
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    session: AsyncSession = Depends(get_session),
) -> PublicMonthSlotsOut:
    master = await MasterRepository(session).by_slug(slug)
    if master is None or not _master_is_available(master):
        raise ApiError("not_found", "master not found", status_code=404)
    service = await ServiceRepository(session).by_id(service_id)
    if service is None or service.master_id != master.id:
        raise ApiError("not_found", "service not found", status_code=404)

    avail = AvailabilityService(session)
    days = await avail.days_with_capacity(master=master, service=service, month=month)
    return PublicMonthSlotsOut(
        days=[PublicMonthDayOut(date=d.isoformat(), has_capacity=has) for d, has in days]
    )


@router.get("/masters/{slug}/slots/day", response_model=list[PublicSlotOut])
async def public_master_slots_day(
    slug: str,
    service_id: UUID,
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    session: AsyncSession = Depends(get_session),
) -> list[PublicSlotOut]:
    master = await MasterRepository(session).by_slug(slug)
    if master is None or not _master_is_available(master):
        raise ApiError("not_found", "master not found", status_code=404)
    service = await ServiceRepository(session).by_id(service_id)
    if service is None or service.master_id != master.id:
        raise ApiError("not_found", "service not found", status_code=404)

    avail = AvailabilityService(session)
    target = date_type.fromisoformat(date)
    slots = await avail.free_slots_for_day(master=master, service=service, day=target)
    return [PublicSlotOut(start_at_utc=s) for s in slots]
```

If `AvailabilityService.days_with_capacity` or `free_slots_for_day` don't exist with those exact names, look at how `src/api/routes/masters.py:92` calls availability and reuse the same helpers. The point is: read existing private endpoints first, then mirror them in the public namespace without auth.

- [ ] **Step 5: Run public tests — confirm pass**

```bash
SENTRY_DSN= uv run pytest tests/test_api_public_bookings.py -v
```

All 3 PASS.

- [ ] **Step 6: Lint + types**

```bash
uv run ruff check src/api/schemas.py src/api/routes/public.py tests/test_api_public_bookings.py
uv run ruff format src/api/schemas.py src/api/routes/public.py tests/test_api_public_bookings.py
uv run mypy src/api/schemas.py src/api/routes/public.py
```

Clean.

- [ ] **Step 7: Commit**

```bash
git add src/api/schemas.py src/api/routes/public.py tests/test_api_public_bookings.py
git commit -m "feat(public): read endpoints — master / services / slots month + day"
```

---

### Task 5: POST `/v1/public/bookings` + master notification

**Files:**
- Modify: `src/services/booking.py` — add `source` parameter to `create_pending`
- Modify: `src/api/routes/public.py` — add POST endpoint
- Modify: `tests/test_api_public_bookings.py` — add tests

- [ ] **Step 1: Extend `BookingService.create_pending` to accept `source`**

In `src/services/booking.py` find `create_pending` (~line 76). Update signature:

```python
    async def create_pending(
        self,
        *,
        master: Master,
        client: Client,
        service: Service,
        start_at: datetime,
        source: str = "client_request",
        now: datetime | None = None,
    ) -> Appointment:
```

Inside the body, replace the hardcoded `source="client_request"` in the `self._repo.create(...)` call with the new parameter:

```python
            appt = await self._repo.create(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at=start_at,
                end_at=end_at,
                status="pending",
                source=source,
                decision_deadline=deadline,
            )
```

- [ ] **Step 2: Add failing tests for POST endpoint**

Append to `tests/test_api_public_bookings.py`:

```python
import secrets
from datetime import datetime, timedelta, timezone


@pytest.mark.asyncio
async def test_public_create_booking_happy_path(session) -> None:
    """End-to-end: master + service exist → POST creates pending appointment."""
    master = Master(
        tg_id=88010,
        name="Booking Anna",
        slug="booking-anna",
        specialty_text="x",
        lang="ru",
        work_hours={"mon": [["09:00", "20:00"]], "tue": [["09:00", "20:00"]],
                    "wed": [["09:00", "20:00"]], "thu": [["09:00", "20:00"]],
                    "fri": [["09:00", "20:00"]], "sat": [["09:00", "20:00"]]},
        is_public=True,
    )
    session.add(master)
    await session.flush()
    svc = Service(master_id=master.id, name="Cut", duration_min=60, active=True)
    session.add(svc)
    await session.commit()

    # Pick a slot at 10:00 UTC on a future Monday
    today = datetime.now(timezone.utc)
    days_to_mon = (7 - today.weekday()) % 7 or 7
    monday = (today + timedelta(days=days_to_mon)).replace(hour=10, minute=0, second=0, microsecond=0)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            "/v1/public/bookings",
            json={
                "master_slug": "booking-anna",
                "service_id": str(svc.id),
                "start_at_utc": monday.isoformat(),
                "client_name": "Mariam",
                "client_phone": "+37493144550",
                "recaptcha_token": None,
            },
        )
    assert r.status_code == 201, r.json()
    body = r.json()
    assert body["status"] == "pending"
    assert UUID(body["id"])
    assert body["telegram_link_url"].startswith("https://t.me/")
    assert "?start=link_" in body["telegram_link_url"]


@pytest.mark.asyncio
async def test_public_create_booking_404_unknown_slug(session) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            "/v1/public/bookings",
            json={
                "master_slug": "no-such-master",
                "service_id": "00000000-0000-0000-0000-000000000000",
                "start_at_utc": "2099-01-01T10:00:00Z",
                "client_name": "X",
                "client_phone": "+37499000000",
                "recaptcha_token": None,
            },
        )
    assert r.status_code == 404
```

- [ ] **Step 3: Run failing test**

```bash
SENTRY_DSN= uv run pytest tests/test_api_public_bookings.py::test_public_create_booking_happy_path -v
```

Expected: FAIL — endpoint doesn't exist.

- [ ] **Step 4: Implement POST endpoint in `src/api/routes/public.py`**

Add at the bottom of the file:

```python
import secrets

from src.api.deps import get_app_bot, get_bot
from src.api.schemas import PublicBookingIn, PublicBookingOut, PublicBookingStatusOut
from src.config import settings
from src.db.models import Appointment, Client, Salon
from src.repositories.appointments import AppointmentRepository
from src.repositories.clients import ClientRepository
from src.services.booking import BookingService
from src.services.reminders import ReminderService
from src.utils.client_notify import notify_user
from src.utils.ratelimit import consume_token
from src.utils.recaptcha import verify_recaptcha
from src.utils.time import now_utc

# Rate-limit windows (per-IP and per-phone-per-master)
_RL_IP_LIMIT = 5
_RL_IP_WINDOW = 60 * 60  # 1 hour
_RL_PHONE_LIMIT = 3
_RL_PHONE_WINDOW = 60 * 60  # 1 hour


def _approve_kb(appointment_id: UUID) -> object:
    """Approve / Reject inline buttons for the master's notification.

    Mirror of bookings._approve_kb so a public booking gets the same
    keyboard. Strings come from the i18n bundle in master.lang context.
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.callback_data.approval import ApprovalCallback
    from src.strings import strings

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.APPT_BTN_CONFIRM,
                    callback_data=ApprovalCallback(
                        action="confirm", appointment_id=appointment_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=strings.APPT_BTN_REJECT,
                    callback_data=ApprovalCallback(
                        action="reject", appointment_id=appointment_id
                    ).pack(),
                ),
            ],
        ]
    )


@router.post("/bookings", response_model=PublicBookingOut, status_code=201)
async def public_create_booking(
    payload: PublicBookingIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    bot: "Bot" = Depends(get_bot),
    app_bot: "Bot | None" = Depends(get_app_bot),
) -> PublicBookingOut:
    """Public web-booking. No auth — only reCAPTCHA + rate-limit defend.

    Flow:
      1. reCAPTCHA verify (if configured)
      2. Rate-limit by IP + by (master, phone)
      3. Resolve master + service
      4. Get-or-create Client by (master_id, phone). Issue link_token
         if Client.tg_id is null (new or web-only client).
      5. Create Appointment via BookingService.create_pending(source="web")
      6. Notify master via existing notify_user + _approve_kb flow,
         using master.lang for strings.
    """
    from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401  (type ref)
    from src.strings import set_current_lang

    # 1. reCAPTCHA
    ok = await verify_recaptcha(payload.recaptcha_token, expected_action="public_booking")
    if not ok:
        raise ApiError("captcha_failed", "captcha verification failed", status_code=400)

    # 2. Rate-limit
    ip = request.client.host if request.client else "unknown"
    redis = request.app.state.redis  # set up by API startup; see notes
    if not await consume_token(redis, f"rl:pubbk:ip:{ip}", limit=_RL_IP_LIMIT, window_sec=_RL_IP_WINDOW):
        raise ApiError("rate_limited", "too many requests, try later", status_code=429)

    # 3. Resolve master + service
    master = await MasterRepository(session).by_slug(payload.master_slug)
    if master is None or not _master_is_available(master):
        raise ApiError("not_found", "master not found", status_code=404)
    service = await ServiceRepository(session).by_id(payload.service_id)
    if service is None or service.master_id != master.id or not service.active:
        raise ApiError("not_found", "service not found", status_code=404)

    # Phone-scoped rate-limit
    if not await consume_token(
        redis,
        f"rl:pubbk:mp:{master.id}:{payload.client_phone}",
        limit=_RL_PHONE_LIMIT,
        window_sec=_RL_PHONE_WINDOW,
    ):
        raise ApiError("rate_limited", "too many bookings, try later", status_code=429)

    # 4. Get-or-create Client
    client_repo = ClientRepository(session)
    client = await client_repo.get_by_phone(master_id=master.id, phone=payload.client_phone)
    if client is None:
        client = Client(
            master_id=master.id,
            phone=payload.client_phone,
            name=payload.client_name.strip(),
            tg_id=None,
            link_token=secrets.token_urlsafe(16),
        )
        session.add(client)
        await session.flush()
    else:
        # Existing client: refresh name (the latest booking-time name wins)
        if payload.client_name.strip():
            client.name = payload.client_name.strip()
        if client.tg_id is None and not client.link_token:
            # Web client without bot link — issue token
            client.link_token = secrets.token_urlsafe(16)

    # 5. Create appointment
    booking_svc = BookingService(session, ReminderService(session))
    try:
        appt = await booking_svc.create_pending(
            master=master,
            client=client,
            service=service,
            start_at=payload.start_at_utc,
            source="web",
        )
    except Exception as exc:
        # SlotAlreadyTaken / IntegrityError surface here
        from src.exceptions import SlotAlreadyTaken

        if isinstance(exc, SlotAlreadyTaken):
            raise ApiError("slot_taken", "slot just taken — pick another", status_code=409) from exc
        raise

    # 6. Notify master
    set_current_lang(master.lang)
    from zoneinfo import ZoneInfo

    from src.strings import strings

    tz = ZoneInfo(master.timezone)
    local = appt.start_at.astimezone(tz)
    weekday = strings.WEEKDAY_SHORT[local.weekday()]
    text = strings.APPT_NOTIFY_MASTER.format(
        name=client.name,
        phone=client.phone or "—",
        service=service.name,
        duration=service.duration_min,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        weekday=weekday,
    )
    sent = await notify_user(
        app_bot=app_bot,
        fallback_bot=bot,
        chat_id=master.tg_id,
        text=text,
        reply_markup=_approve_kb(appt.id),
    )
    if sent is not None:
        appt.master_notify_chat_id = sent.chat_id
        appt.master_notify_msg_id = sent.message_id
        appt.master_notify_via = sent.via
        await session.commit()

    return PublicBookingOut(
        id=appt.id,
        master_name=master.name,
        service_name=service.name,
        start_at=appt.start_at,
        status=appt.status,
        telegram_link_url=f"https://t.me/{settings.app_bot_username}?start=link_{client.link_token}"
        if client.link_token
        else f"https://t.me/{settings.app_bot_username}?start=master_{master.slug}",
    )
```

NOTE: The endpoint references `request.app.state.redis`. If the FastAPI app doesn't yet expose Redis at startup, add it. Check `src/api/main.py`:

- If there's a startup event already opening a Redis client → set `app.state.redis = redis` there
- Otherwise add a startup hook:

```python
from redis.asyncio import Redis

@app.on_event("startup")
async def _open_redis() -> None:
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=False)


@app.on_event("shutdown")
async def _close_redis() -> None:
    redis = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()
```

If this hook already exists for another purpose, just reuse it.

Also at the top of `public.py`, add the FastAPI `Request` import:

```python
from fastapi import Request
```

- [ ] **Step 3a: Find or create `ClientRepository.get_by_phone`**

Open `src/repositories/clients.py` (might be at that path or named differently — check). If `get_by_phone(master_id, phone)` doesn't exist, add:

```python
    async def get_by_phone(self, *, master_id: UUID, phone: str) -> Client | None:
        return await self._session.scalar(
            select(Client).where(Client.master_id == master_id, Client.phone == phone)
        )
```

If the repository file doesn't exist (clients are queried inline in services), create `src/repositories/clients.py`:

```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client


class ClientRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_phone(self, *, master_id: UUID, phone: str) -> Client | None:
        return await self._session.scalar(
            select(Client).where(Client.master_id == master_id, Client.phone == phone)
        )
```

- [ ] **Step 4: Run tests**

```bash
SENTRY_DSN= uv run pytest tests/test_api_public_bookings.py -v
```

Expected: all PASS (5 tests including the original 3).

If a test fails because of the redis hook not being set up — the conftest may need to add a Redis instance to `app.state.redis`. Check `tests/conftest.py` and add a fixture if needed. Pattern:

```python
@pytest.fixture(autouse=True)
async def _redis_in_app_state() -> AsyncIterator[None]:
    from redis.asyncio import Redis
    from src.api.main import app
    r = Redis.from_url("redis://localhost:6379/9", decode_responses=False)
    app.state.redis = r
    yield
    await r.aclose()
```

- [ ] **Step 5: Lint + types**

```bash
uv run ruff check src/api/routes/public.py src/services/booking.py src/repositories/clients.py
uv run ruff format src/api/routes/public.py src/services/booking.py src/repositories/clients.py
uv run mypy src/api/routes/public.py src/services/booking.py src/repositories/clients.py
```

Clean.

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/public.py src/services/booking.py src/repositories/clients.py src/api/main.py tests/test_api_public_bookings.py tests/conftest.py
git commit -m "feat(public): POST /v1/public/bookings — web-form booking endpoint

reCAPTCHA + rate-limit defended; reuses existing master-notify flow
through notify_user. New clients get a link_token for post-booking
Telegram opt-in."
```

---

### Task 6: GET `/v1/public/bookings/{id}` — status check

**Files:**
- Modify: `src/api/routes/public.py`
- Modify: `tests/test_api_public_bookings.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_api_public_bookings.py`:

```python
@pytest.mark.asyncio
async def test_public_booking_status_returns_current(session) -> None:
    """After booking, GET /v1/public/bookings/{id} returns its status."""
    master = Master(
        tg_id=88020,
        name="Status Anna",
        slug="status-anna",
        specialty_text="x",
        lang="ru",
        work_hours={"mon": [["09:00", "20:00"]], "tue": [["09:00", "20:00"]],
                    "wed": [["09:00", "20:00"]], "thu": [["09:00", "20:00"]],
                    "fri": [["09:00", "20:00"]], "sat": [["09:00", "20:00"]]},
        is_public=True,
    )
    session.add(master)
    await session.flush()
    svc = Service(master_id=master.id, name="Cut", duration_min=60, active=True)
    session.add(svc)
    await session.commit()

    today = datetime.now(timezone.utc)
    days_to_mon = (7 - today.weekday()) % 7 or 7
    monday = (today + timedelta(days=days_to_mon)).replace(hour=11, minute=0, second=0, microsecond=0)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        create = await ac.post(
            "/v1/public/bookings",
            json={
                "master_slug": "status-anna",
                "service_id": str(svc.id),
                "start_at_utc": monday.isoformat(),
                "client_name": "Status",
                "client_phone": "+37493144551",
                "recaptcha_token": None,
            },
        )
        assert create.status_code == 201
        booking_id = create.json()["id"]

        status = await ac.get(f"/v1/public/bookings/{booking_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "pending"
    assert status.json()["service_name"] == "Cut"
```

- [ ] **Step 2: Run, confirm fail**

```bash
SENTRY_DSN= uv run pytest tests/test_api_public_bookings.py::test_public_booking_status_returns_current -v
```

Expected: 404.

- [ ] **Step 3: Implement endpoint**

Add to `src/api/routes/public.py`:

```python
@router.get("/bookings/{booking_id}", response_model=PublicBookingStatusOut)
async def public_booking_status(
    booking_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PublicBookingStatusOut:
    """Status check by UUID (UUID acts as bearer token).

    Returns minimal info — for the lander's localStorage refresh on
    return visits. Doesn't expose phone/tg_id; doesn't allow status
    mutations.
    """
    from src.db.models import Service as ServiceModel

    appt = await session.scalar(
        select(Appointment).where(Appointment.id == booking_id)
    )
    if appt is None:
        raise ApiError("not_found", "booking not found", status_code=404)
    master = await session.scalar(
        select(Master).where(Master.id == appt.master_id)
    )
    service = await session.scalar(
        select(ServiceModel).where(ServiceModel.id == appt.service_id)
    )
    if master is None or service is None:
        raise ApiError("not_found", "booking not found", status_code=404)
    return PublicBookingStatusOut(
        id=appt.id,
        status=appt.status,
        master_name=master.name,
        service_name=service.name,
        start_at=appt.start_at,
    )
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
SENTRY_DSN= uv run pytest tests/test_api_public_bookings.py -v
```

All PASS.

- [ ] **Step 5: Lint**

```bash
uv run ruff check src/api/routes/public.py tests/test_api_public_bookings.py
uv run ruff format src/api/routes/public.py tests/test_api_public_bookings.py
uv run mypy src/api/routes/public.py
```

Clean.

- [ ] **Step 6: Commit**

```bash
git add src/api/routes/public.py tests/test_api_public_bookings.py
git commit -m "feat(public): GET /v1/public/bookings/{id} — status refresh"
```

---

### Task 7: Bot `/start link_<token>` deep-link handler

**Files:**
- Modify: `src/app_bot/handlers.py`
- Modify: `tests/test_app_bot_handlers.py`

- [ ] **Step 1: Add tests for new `link` kind + handler logic**

Append to `tests/test_app_bot_handlers.py`:

```python
def test_inline_label_link_armenian() -> None:
    from src.app_bot.handlers import _inline_label_for
    assert _inline_label_for("link_abc123", "hy") == "Բացել իմ գրանցումը"


def test_inline_label_link_russian() -> None:
    from src.app_bot.handlers import _inline_label_for
    assert _inline_label_for("link_abc123", "ru") == "Открыть мою запись"


def test_kind_for_link() -> None:
    from src.app_bot.handlers import _kind_for
    assert _kind_for("link_abc123") == "link"
```

- [ ] **Step 2: Run, confirm fail**

```bash
SENTRY_DSN= uv run pytest tests/test_app_bot_handlers.py -k "link" -v
```

Expected: KeyError or assertion mismatch — `link` kind doesn't exist.

- [ ] **Step 3: Add `link` kind to `_kind_for` and labels in `_INLINE_LABELS` / `_WELCOME_TEXTS`**

In `src/app_bot/handlers.py`:

Find `_kind_for(start_param)`. Add a branch BEFORE the catch-all `default`:

```python
def _kind_for(start_param: str | None) -> str:
    if not start_param:
        return "default"
    if start_param == "signup":
        return "signup"
    if start_param == "signup-salon":
        return "signup-salon"
    if start_param.startswith("invite_"):
        return "invite"
    if start_param.startswith("master_"):
        return "master_link"
    if start_param.startswith("salon_"):
        return "salon_link"
    if start_param.startswith("link_"):
        return "link"
    return "default"
```

In `_INLINE_LABELS` add 3 rows:

```python
    ("hy", "link"): "Բացել իմ գրանցումը",
    ("ru", "link"): "Открыть мою запись",
    ("en", "link"): "Open my booking",
```

In `_WELCOME_TEXTS` add 3 rows:

```python
    ("hy", "link"): "Բացիր հավելվածը՝ քո գրանցումը տեսնելու համար.",
    ("ru", "link"): "Открой приложение, чтобы увидеть свою запись.",
    ("en", "link"): "Open the app to see your booking.",
```

- [ ] **Step 4: Add the actual link-binding logic in `handle_start`**

Find the body of `handle_start` (around lines 70-200). Right after `start_param = ...` extraction, add a special path for `link_<token>`:

```python
    # Web-booking opt-in: bind tg_id to Client by one-shot token.
    if start_param and start_param.startswith("link_"):
        from src.db.models import Client as ClientModel

        token = start_param[len("link_"):]
        if token and session is not None and user_tg_id is not None:
            client = await session.scalar(
                select(ClientModel).where(ClientModel.link_token == token)
            )
            if client is not None and (client.tg_id is None or client.tg_id == user_tg_id):
                client.tg_id = user_tg_id
                client.link_token = None
                await session.commit()
                log.info("link_token_bound", tg_id=user_tg_id, client_id=str(client.id))
            elif client is not None:
                log.warning("link_token_owned_by_another", tg_id=user_tg_id, owner=client.tg_id)
            # If token not found — silently ignore; user still gets the standard
            # welcome flow below
```

This block sits before the existing `saved_lang = await _lookup_saved_lang(...)` line.

- [ ] **Step 5: Run all bot tests**

```bash
SENTRY_DSN= uv run pytest tests/test_app_bot_handlers.py -v
```

All PASS.

- [ ] **Step 6: Lint + types**

```bash
uv run ruff check src/app_bot/handlers.py tests/test_app_bot_handlers.py
uv run ruff format src/app_bot/handlers.py tests/test_app_bot_handlers.py
uv run mypy src/app_bot/handlers.py
```

Clean.

- [ ] **Step 7: Commit**

```bash
git add src/app_bot/handlers.py tests/test_app_bot_handlers.py
git commit -m "feat(app_bot): /start link_<token> binds tg_id to Client from web booking"
```

---

### Task 8: Phase 1 final + push

- [ ] **Step 1: Full pytest sweep**

```bash
SENTRY_DSN= uv run pytest --tb=no -q | tail -3
```

Expected: 575+ PASS.

- [ ] **Step 2: Lint + format + mypy**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src/
```

Clean.

- [ ] **Step 3: Merge to main + push (auto-deploy)**

```bash
git checkout main
git merge --no-ff feat/public-booking -m "Merge: public web booking endpoints + bot link_<token> handler"
git push origin main
```

- [ ] **Step 4: Wait for CI + deploy**

Poll until deploy completes:

```bash
until curl -s "https://api.github.com/repos/VanikVardanyan/grancvi/actions/runs?branch=main&per_page=2" | python3 -c "import json,sys; runs=json.load(sys.stdin).get('workflow_runs',[]); d=[r for r in runs if r['name']=='deploy']; sys.exit(0 if d and d[0]['status']=='completed' else 1)" 2>/dev/null; do
  printf "."
  sleep 15
done
echo
curl -sf https://api.grancvi.am/v1/health && echo " | api up"
```

- [ ] **Step 5: Smoke-test the new endpoints**

```bash
# An existing master from prod — pick any public one
curl -s https://api.grancvi.am/v1/public/masters/<some-real-slug> | head
```

Expected: 200 with master profile.

---

## Phase 2 — Frontend lander

### Task 9: Replace `r.html` with the booking wizard wired to real API

**Files:**
- Modify: `grancvi-landing/r.html`

- [ ] **Step 1: Read current `r.html`**

```bash
cd /Users/vanik/Desktop/projects/working-projects/grancvi-landing
cat r.html | head -50
```

Currently it's the smart-redirect into TMA. We're keeping the redirect for Telegram users (so they continue into TMA as before), but for non-Telegram users we render the real booking form.

- [ ] **Step 2: Replace `r.html` with the wired-up form**

Use `book-mockup.html` as the base — copy it to `r.html`, then make 3 production-ready changes:

1. At the top of the `<script>`, before all rendering, detect Telegram client and redirect:

```javascript
// If opened in Telegram client → redirect to TMA as the old r.html did.
// Detection: presence of Telegram.WebApp object OR UA marker.
function isInTelegram() {
  if (typeof window.Telegram !== "undefined" && window.Telegram?.WebApp) return true;
  return /Telegram/i.test(navigator.userAgent);
}

if (isInTelegram()) {
  // Bounce to TMA with this slug; matches old r.html behavior
  const slug = window.location.pathname.replace(/^\/+/, "").split("/")[0];
  if (slug) {
    window.location.href = `https://t.me/grancviWebBot?start=master_${encodeURIComponent(slug)}`;
  } else {
    window.location.href = "https://t.me/grancviWebBot";
  }
  // Stop further script execution
  throw new Error("redirecting to telegram");
}
```

2. Replace the mock data and mock submit with real API calls:

   a. The slug comes from URL: `const MASTER_SLUG = window.location.pathname.replace(/^\/+/, "").split("/")[0];`

   b. Master profile: `fetch('/v1/public/masters/' + MASTER_SLUG)` — sets MASTER_NAME from response.

   c. Services: `fetch('/v1/public/masters/' + MASTER_SLUG + '/services')` — replaces `MOCK_SERVICES`. Each item has `{id, name, duration_min, price_amd}`.

   d. Month slots: `fetch('/v1/public/masters/' + MASTER_SLUG + '/slots/month?service_id=' + state.service.id + '&month=' + cursorMonthStr)` — array of `{date, has_capacity}` updates which days are highlighted.

   e. Day slots: `fetch('/v1/public/masters/' + MASTER_SLUG + '/slots/day?service_id=' + state.service.id + '&date=' + state.date)` — array of `{start_at_utc}`. Convert to local time for display.

   f. Submit: `fetch('/v1/public/bookings', {method: 'POST', body: JSON.stringify({...})})`. On success, store id + telegram_link_url to localStorage and render success screen.

3. Localstorage status refresh: on page load, for each booking in localStorage, fetch `/v1/public/bookings/{id}` and update its `status`.

For the production html, see this complete file content:

NOTE: due to file length (~700 lines), implementer should:
- Open `book-mockup.html` (the approved UI reference)
- Copy it to `r.html`
- Apply the three changes above:
  - Add Telegram-detect + redirect at the very top of the script
  - Replace mock data (`MOCK_SERVICES`, `MOCK_TIMES`, `MASTER_NAME`) with API fetches that populate `state` from real responses
  - Replace mock submit (`fakeId = "mock-..."`) with real `fetch('/v1/public/bookings', ...)`. Use `response.id` and `response.telegram_link_url` from the actual API.

Keep all UI structure, i18n, calendar, phone mask, success-screen, localStorage-render — they're unchanged.

The exact API client (vanilla `fetch`) lives at the top of the script:

```javascript
const API_BASE = "/v1/public";

async function api(path, opts) {
  const r = await fetch(API_BASE + path, opts);
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.error?.code || `http_${r.status}`);
  }
  return r.json();
}
```

Use it like:

```javascript
// Load services on init
async function loadServices() {
  try {
    SERVICES = await api(`/masters/${MASTER_SLUG}/services`);
    renderServices();
  } catch (err) {
    showError(err.message);
  }
}
```

Submit:

```javascript
submitBtn.addEventListener("click", async () => {
  submitBtn.disabled = true;
  try {
    const result = await api("/bookings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        master_slug: MASTER_SLUG,
        service_id: state.service.id,
        start_at_utc: state.slotUtc,  // store the UTC ISO from slots/day response
        client_name: state.name,
        client_phone: "+374" + state.phone,
        recaptcha_token: null,
      }),
    });
    persistBooking(result);
    renderSuccess(result);
    setStep("success");
  } catch (err) {
    submitBtn.disabled = false;
    showError(err.message);
  }
});
```

- [ ] **Step 3: Manual test locally**

```bash
cd grancvi-landing
python3 -m http.server 8888
```

Open `http://localhost:8888/r.html` (since we're not at the right slug, the API calls will 404 — that's expected; just sanity-check that the JS runs without errors).

- [ ] **Step 4: Commit**

```bash
git add r.html
git commit -m "feat(lander): r.html — booking wizard wired to real /v1/public API

Telegram clients still bounce to TMA (existing behavior).
Other browsers see a 3-step booking wizard wired to:
- GET /v1/public/masters/{slug}
- GET /v1/public/masters/{slug}/services
- GET /v1/public/masters/{slug}/slots/month
- GET /v1/public/masters/{slug}/slots/day
- POST /v1/public/bookings
- GET /v1/public/bookings/{id}  (for localStorage status refresh)"
```

---

### Task 10: Deploy lander

- [ ] **Step 1: scp r.html to VPS**

```bash
scp -i ~/.ssh/grancvi-deploy r.html deploy@94.130.149.91:/var/www/grancvi-landing/
```

- [ ] **Step 2: Verify**

Open in non-Telegram browser:

```bash
curl -s https://grancvi.am/$(real_slug) | head -10
```

Expected: HTML with booking wizard. Open in browser to test the full flow.

---

## Phase 3 — Frontend TMA

### Task 11: Handle `link_<token>` start_param in App.tsx

**Files:**
- Modify: `grancvi-web/src/App.tsx`

- [ ] **Step 1: Add to RoleRouter deep-link branches**

In `src/App.tsx`, find the deep-link handling block (around lines 70-95). After the `signup-salon` branch:

```typescript
  if (!consumed && startParam === "signup-salon" && me.data?.role === "client") {
    return <Navigate to="/register/self-salon" replace />;
  }
```

Add:

```typescript
  // Web-booking opt-in: client tapped "Open in Telegram" on the lander
  // success screen → bot already bound their tg_id → MyBookings has the
  // appointment. Just route them there.
  if (!consumed && startParam.startsWith("link_")) {
    return <Navigate to="/me" replace />;
  }
```

- [ ] **Step 2: Compile**

```bash
cd /Users/vanik/Desktop/projects/working-projects/grancvi-web
pnpm exec tsc -b --noEmit
```

Clean.

- [ ] **Step 3: Build**

```bash
pnpm build
```

Clean.

- [ ] **Step 4: Commit**

```bash
git add src/App.tsx
git commit -m "feat(routes): link_<token> start_param routes to /me

The bot has already bound Client.tg_id by the time TMA opens, so
MyBookings will find the web-created appointment automatically."
```

- [ ] **Step 5: Deploy via scp**

```bash
scp -i ~/.ssh/grancvi-deploy -r dist/* deploy@94.130.149.91:/var/www/jampord-app/
```

Verify bundle:

```bash
curl -s https://app.grancvi.am/ | grep -oE 'index-[^"]+\.js' | head -1
```

---

## Phase 4 — Verification

### Task 12: Prod E2E smoke

**User-driven test**:

- [ ] **Step 1: Pick an existing master slug from DB** (e.g. `barbergor`, `mashh`)

- [ ] **Step 2: Open `https://grancvi.am/<slug>` in a non-Telegram browser** (Chrome on desktop, or Safari on iOS in the regular browser, NOT inside Telegram)

Expected:
- Step 1 wizard shows: master card + services list
- Step 2: month-grid calendar with available days highlighted
- Pick a date → smooth-scroll to time picker → see slots
- Pick time → next
- Step 3: enter name + phone (+374 mask) → reCAPTCHA score (if configured) → submit

- [ ] **Step 3: Verify master receives Telegram notification with approve/reject buttons**

Check the master's Telegram — should arrive within seconds.

- [ ] **Step 4: Tap «Открыть в Telegram» on success screen**

Should:
1. Open `t.me/grancviWebBot?start=link_<token>`
2. Bot binds tg_id, sends "Open my booking" inline button
3. Tap button → TMA opens → `/me` route → see the booking

- [ ] **Step 5: Refresh `https://grancvi.am/<slug>` (still in browser)**

Should show "Your bookings with <Master>" block at top with the saved appointment.

- [ ] **Step 6: As master, approve the booking via TMA**

Verify status updates work — refresh `https://grancvi.am/<slug>` again — booking should now show `confirmed` status (refreshed via GET /v1/public/bookings/{id}).

- [ ] **Step 7: Cleanup**

Delete the test booking via `/admin` or directly via SQL on prod, so the master's calendar is clean.
