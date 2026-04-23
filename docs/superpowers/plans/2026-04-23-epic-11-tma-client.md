# Epic 11 — Telegram Mini App Client Booking

> **For agentic workers:** This plan has two streams — **backend** (implementer: AI/controller) and **frontend** (implementer: user, 6yr React). Backend tasks use TDD; frontend tasks give high-level structure and let the React dev make idiomatic choices.

**Goal:** Ship a Telegram Mini App that replaces the client-facing booking flow with a proper web UI, running in parallel with the existing `@GrancviBot`. New bot `@GrancviAppBot` serves as the TMA launcher. Master experience stays in the original bot unchanged.

**Architecture:**
- Shared PostgreSQL (same DB as current bot — `botik`)
- Shared SQLAlchemy models, repositories, and service layer (`src/services/booking.py`, `src/services/availability.py`, etc.)
- New FastAPI app (`src/api/`) exposes REST endpoints consumed by the web frontend
- New bot `@GrancviAppBot` (minimal: `/start` → WebApp button) written as a new aiogram entrypoint (`src/app_bot_main.py`)
- Frontend: Vite + React + TypeScript + Tailwind + `@telegram-apps/sdk-react` + `@telegram-apps/telegram-ui`, deployed as static files
- Reverse proxy: Nginx with Let's Encrypt / Cloudflare for SSL termination

**Tech Stack additions:** `fastapi`, `uvicorn`, `python-jose[cryptography]` (for HMAC initData verify), frontend via Vite+React

**Domain:** `jampord.am` (user-owned)
- `api.jampord.am` → FastAPI (via Nginx)
- `app.jampord.am` → React SPA (static via Nginx)

**Out of scope (deferred to Epic 12+):**
- Salon client-facing features in TMA (salon landing page, grouping)
- Full migration of old bot — old bot stays for now; we may redirect its `/start master_<slug>` to TMA later
- Photos, portfolios, reviews (MVP is functional parity with current bot)
- Payments

**Rollout strategy:** Live in parallel. Current masters/clients unaffected. New masters can point clients to either bot. When TMA proves better, old client flow becomes a thin redirect.

---

## Streams

- **Backend** (Tasks B1–B9): FastAPI, auth, endpoints, deployment. Implementer works in this repo.
- **Frontend** (Tasks F1–F8): React SPA. Implementer (the user) works in a new repo or a sibling folder — **recommended:** `/Users/vanik/Desktop/projects/working-projects/tg-bot-web/` as a separate git repo to keep Python + JS toolchains clean.
- **Ops** (Tasks O1–O3): DNS, SSL, deploy pipeline. Mixed.

Backend and frontend can progress in parallel once the API contract (Task B3) is locked.

---

## API Contract (v0)

All endpoints served at `https://api.jampord.am/v1/...`. Auth via header `X-Telegram-Init-Data: <raw initData string>`.

```
GET  /v1/masters/by-slug/{slug}
       → 200 { id, name, specialty, is_public, timezone }
       → 404

GET  /v1/masters/{id}/services
       → 200 [{ id, name, duration_min, price_amd? }, ...]

GET  /v1/masters/{id}/slots?service_id=<uuid>&month=YYYY-MM
       → 200 { days: [{ date, free_count, has_capacity }], ... }

GET  /v1/masters/{id}/slots?service_id=<uuid>&date=YYYY-MM-DD
       → 200 [{ start_at_utc }, ...]  (only free slots for that day)

POST /v1/bookings
  body: { master_id, service_id, start_at_utc, client_name, client_phone? }
       → 201 { appointment_id, status: "pending" | "confirmed" }
       → 409 slot_taken

GET  /v1/bookings/mine
       → 200 [{ id, master_name, service_name, start_at_utc, status }, ...]
         (client's upcoming appointments by tg_id from initData)

POST /v1/bookings/{id}/cancel
       → 200 { ok: true }
       → 403 not_owner
       → 409 cannot_cancel (already passed / already cancelled)
```

**Error shape:** `{ error: { code: "slot_taken", message: "..." } }` with HTTP status matching.

**Auth rule:** every endpoint validates `X-Telegram-Init-Data`:
1. Parse it as URL-encoded form
2. Extract `hash` param
3. Build `data_check_string` (all params except `hash`, sorted, `key=value` joined with `\n`)
4. Compute `HMAC-SHA256(secret_key, data_check_string)` where `secret_key = HMAC-SHA256("WebAppData", BOT_TOKEN_APPBOT)`
5. Compare to `hash` param
6. Also verify `auth_date` is within 24h of now
7. Decode `user` JSON → inject `tg_user` into request

---

## Backend Tasks

### Task B1: Add FastAPI scaffolding + dependency

**Files:**
- Create: `src/api/__init__.py`
- Create: `src/api/main.py` — FastAPI app with healthcheck
- Modify: `pyproject.toml` — add `fastapi>=0.110`, `uvicorn[standard]>=0.29`
- Create: `tests/test_api_health.py`

- [ ] **Step 1: Test**

```python
# tests/test_api_health.py
from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app


def test_health_endpoint() -> None:
    client = TestClient(app)
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2: Run — FAIL**

`uv run pytest tests/test_api_health.py`

- [ ] **Step 3: Install deps + implement**

```toml
# pyproject.toml dependencies
"fastapi>=0.110,<1",
"uvicorn[standard]>=0.29",
"httpx>=0.27",   # pulls in for TestClient
```

Then:
```
uv sync
```

```python
# src/api/main.py
from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="grancvi api", version="0.1.0", docs_url=None, redoc_url=None)


@app.get("/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Pass**

- [ ] **Step 5: Commit**

```
git commit -m "feat(api): FastAPI skeleton with /v1/health"
```

---

### Task B2: Telegram initData validator

**Files:**
- Create: `src/api/auth.py` — HMAC validator + FastAPI dependency
- Create: `tests/test_api_auth.py`

- [ ] **Step 1: Test**

```python
# tests/test_api_auth.py
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from src.api.auth import InvalidInitData, parse_and_validate_init_data


def _sign(data: dict[str, str], bot_token: str) -> str:
    """Produce a valid Telegram initData string for tests."""
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs = sorted((k, v) for k, v in data.items() if k != "hash")
    check = "\n".join(f"{k}={v}" for k, v in pairs)
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    data["hash"] = digest
    return urlencode(data)


def test_valid_init_data_returns_user_dict() -> None:
    token = "12345:abc"
    data = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": 42, "first_name": "A"}),
    }
    raw = _sign(data, token)
    user = parse_and_validate_init_data(raw, bot_token=token)
    assert user["id"] == 42


def test_tampered_hash_rejected() -> None:
    token = "12345:abc"
    data = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": 42, "first_name": "A"}),
    }
    raw = _sign(data, token)
    tampered = raw.replace("A", "B")
    with pytest.raises(InvalidInitData):
        parse_and_validate_init_data(tampered, bot_token=token)


def test_expired_rejected() -> None:
    token = "12345:abc"
    data = {
        "auth_date": str(int(time.time()) - 48 * 3600),
        "user": json.dumps({"id": 42, "first_name": "A"}),
    }
    raw = _sign(data, token)
    with pytest.raises(InvalidInitData):
        parse_and_validate_init_data(raw, bot_token=token, max_age_seconds=24 * 3600)
```

- [ ] **Step 2: Fail**

- [ ] **Step 3: Implement**

```python
# src/api/auth.py
from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException

from src.config import settings


class InvalidInitData(Exception):
    pass


def parse_and_validate_init_data(
    raw: str, *, bot_token: str, max_age_seconds: int = 24 * 3600
) -> dict[str, Any]:
    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    provided_hash = pairs.pop("hash", None)
    if not provided_hash:
        raise InvalidInitData("missing hash")

    check_str = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, provided_hash):
        raise InvalidInitData("hash mismatch")

    auth_date = int(pairs.get("auth_date", "0"))
    if abs(time.time() - auth_date) > max_age_seconds:
        raise InvalidInitData("expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InvalidInitData("missing user")
    return json.loads(user_raw)  # type: ignore[no-any-return]


async def require_tg_user(
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    try:
        return parse_and_validate_init_data(
            x_telegram_init_data, bot_token=settings.app_bot_token
        )
    except InvalidInitData as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
```

Add to `src/config.py`:
```python
app_bot_token: str = ""  # @GrancviAppBot token; empty in tests
```

- [ ] **Step 4: Pass**
- [ ] **Step 5: Commit**

```
git commit -m "feat(api): Telegram initData HMAC validator + FastAPI dependency"
```

---

### Task B3: Booking endpoints

**Files:**
- Create: `src/api/routes/bookings.py`
- Create: `src/api/routes/masters.py`
- Modify: `src/api/main.py` — include routers
- Create: `tests/test_api_bookings.py`

Each endpoint:
1. Validates initData → `tg_user`
2. Loads master / service / client via existing repositories
3. Calls existing service (`BookingService`, `AvailabilityService`) — no duplication of business logic
4. Returns JSON

Full implementation of each endpoint follows the API contract at the top. Key detail: POST `/v1/bookings` must:
1. Upsert `Client` by `(master_id, phone)` if phone present; else create anonymous (reuse `ClientRepository.upsert_by_phone` / `create_anonymous`).
2. Set `Client.tg_id = tg_user["id"]` on the client row.
3. Call `BookingService.create_manual(...)` with `source="client_request"`, wrap in `SlotAlreadyTaken` → 409.
4. Fire `ReminderService.schedule_for_appointment`.
5. Notify master via `@GrancviBot` (the OLD bot) — the app bot shouldn't send it, keeps notifications in the original channel. Use `aiogram.Bot(settings.bot_token)` to send.

Tests cover: valid booking, slot taken → 409, unauthenticated → 401, cancel by owner, cancel by non-owner → 403.

- [ ] **Full test code:** see pattern at `tests/test_handlers_client_booking.py`, adapt to `fastapi.testclient.TestClient`. Use `monkeypatch` to stub `require_tg_user` with a fake user for each test.
- [ ] **Implement endpoints**
- [ ] **Tests pass, ruff+mypy clean**
- [ ] **Commit:** `feat(api): booking endpoints with initData auth`

---

### Task B4: App-bot launcher (new Telegram bot)

**Files:**
- Create: `src/app_bot_main.py` — entrypoint for `@GrancviAppBot`
- Create: `src/app_bot/__init__.py`
- Create: `src/app_bot/handlers.py` — single `/start` handler sending WebAppInfo button
- Modify: `pyproject.toml` — add script entrypoint if needed
- Modify: `docker-compose.prod.yml` — add `app_bot` service

- [ ] Implement `/start` handler that replies with:
  ```
  Открой запись в пару тапов:
  [🚀 Открыть]   ← WebAppInfo(url="https://app.jampord.am")
  ```
- [ ] Second `/start {slug}` also works — passes slug to frontend via `start_param`: `https://app.jampord.am?tgWebAppStartParam={slug}`
- [ ] No DB middleware needed — app bot is stateless
- [ ] Tests: minimal, just assert reply text + button

- [ ] **Commit:** `feat(app_bot): new @GrancviAppBot launcher with WebApp button`

---

### Task B5: Docker Compose updates

**Files:**
- Modify: `docker-compose.prod.yml` — add `api`, `app_bot`, `nginx` services

- [ ] `api` service: same image as `app`, but command `uvicorn src.api.main:app --host 0.0.0.0 --port 8000`
- [ ] `app_bot` service: same image, command `python -m src.app_bot_main`, env `APP_BOT_TOKEN`
- [ ] `nginx` service: reverse proxy for `api.jampord.am` → `api:8000` and `app.jampord.am` → static volume
- [ ] Volumes: `./web-dist:/usr/share/nginx/html:ro` (mounted from frontend build output)
- [ ] **Commit:** `chore: docker-compose for api + app_bot + nginx`

---

### Task B6: Nginx + SSL config

**Files:**
- Create: `deploy/nginx/api.conf`
- Create: `deploy/nginx/app.conf`
- Create: `deploy/nginx/Dockerfile`

- [ ] Minimal Nginx configs per subdomain with SSL block
- [ ] Use Let's Encrypt via certbot run manually on first deploy (or Cloudflare Origin Cert if user prefers)
- [ ] Add `certbot` service or run out-of-band once, mount `/etc/letsencrypt`
- [ ] Test configs locally with `nginx -t`
- [ ] **Commit:** `chore: nginx reverse-proxy + SSL configs for jampord.am`

---

### Task B7: Rate limiting + CORS

**Files:**
- Modify: `src/api/main.py` — add CORS middleware allowing only `https://app.jampord.am`
- Modify: `src/api/main.py` — basic rate limiting via `slowapi` (optional)

- [ ] CORS: strict origin, allow `X-Telegram-Init-Data` header
- [ ] Skip rate limiting for MVP unless abuse appears
- [ ] **Commit:** `feat(api): CORS restricted to app.jampord.am`

---

### Task B8: Integration smoke test

**Files:**
- Create: `tests/test_api_e2e.py` — one test that hits multiple endpoints in sequence

- [ ] Master → services → slots → book → cancel. All with signed initData.
- [ ] **Commit:** `test(api): end-to-end smoke test`

---

### Task B9: Deploy to prod

- [ ] SSH to VPS, pull main, `docker compose -f docker-compose.prod.yml up -d`
- [ ] Verify `curl https://api.jampord.am/v1/health` returns `{"status":"ok"}`
- [ ] Verify `@GrancviAppBot /start` works
- [ ] **Commit:** n/a — runtime check only

---

## Frontend Tasks (React)

**Setup in a new repo** to keep toolchains clean:

```
cd /Users/vanik/Desktop/projects/working-projects
mkdir grancvi-web && cd grancvi-web
pnpm create vite@latest . -- --template react-ts
pnpm add @telegram-apps/sdk-react @tanstack/react-query axios
pnpm add -D tailwindcss postcss autoprefixer
pnpm dlx tailwindcss init -p
# optional for native look:
pnpm add @telegram-apps/telegram-ui
```

### Task F1: Boilerplate + TMA SDK bootstrap

- [ ] Set up Vite + React + TS + Tailwind
- [ ] Integrate `@telegram-apps/sdk-react` — call `init()`, expose `useInitDataRaw()`
- [ ] Router (react-router-dom) with routes: `/` (catalog), `/m/:slug` (master), `/m/:slug/book` (booking flow), `/me` (my bookings)
- [ ] API client: axios instance that auto-attaches `X-Telegram-Init-Data` header from TMA SDK
- [ ] Commit first version in separate repo

### Task F2: Master page + service picker

- [ ] `useMaster(slug)` hook calling `GET /v1/masters/by-slug/{slug}`
- [ ] `useServices(masterId)` hook
- [ ] Service list component with name + duration + price (future). Tap → next step.

### Task F3: Date picker (month view)

- [ ] `useMonthSlots(masterId, serviceId, month)` — renders calendar grid with day loads
- [ ] Highlight dates with free slots; grey out full/past days
- [ ] Tap → slot picker

### Task F4: Slot picker

- [ ] `useSlots(masterId, serviceId, date)` — shows free slots as buttons
- [ ] Tap → confirmation screen

### Task F5: Confirmation + booking submission

- [ ] Read client name from Telegram user first_name (prefill) but let them edit
- [ ] Phone field optional
- [ ] On submit → `POST /v1/bookings`
- [ ] Show success screen with "back to catalog" button
- [ ] Handle `409 slot_taken` → go back to slot picker with fresh data

### Task F6: My bookings + cancel

- [ ] Route `/me` — list of upcoming bookings
- [ ] Each row: master name, service, time, status
- [ ] "Cancel" button → confirms → `POST /v1/bookings/{id}/cancel`

### Task F7: Catalog (root `/`)

- [ ] List of public masters (future: salon grouping)
- [ ] MVP: just a list of cards, tap → master page

### Task F8: Polish + Telegram UX

- [ ] Use Telegram theme params (light/dark auto)
- [ ] `MainButton` for primary CTA on each step ("Выбрать время", "Подтвердить запись")
- [ ] `BackButton` for navigation
- [ ] Haptic feedback on tap events
- [ ] Error toast with Telegram popup

---

## Ops Tasks

### Task O1: DNS setup

- [ ] Add A record: `api.jampord.am` → 94.130.149.91
- [ ] Add A record: `app.jampord.am` → 94.130.149.91
- [ ] Verify DNS propagation (`dig api.jampord.am`)

### Task O2: SSL certificates

- [ ] Install certbot on VPS, run `certbot --nginx -d api.jampord.am -d app.jampord.am`
- [ ] Verify cert renewal cron
- [ ] Document in `docs/deployment/README.md`

### Task O3: CI: frontend build & deploy

- [ ] GitHub Action in `grancvi-web` repo: on push to main, build → scp to VPS `/opt/tg-bot/web-dist/`
- [ ] OR: build locally and commit dist to a branch (simpler MVP)

---

## Rollout

**Week 1 target:** Tasks B1-B4, O1-O2, F1 ready. `GET /v1/health` works publicly. `@GrancviAppBot` opens a blank TMA that just shows "Hello from TMA".

**Week 2 target:** Full booking flow end-to-end. Test with our own two masters in prod.

**Week 3 target:** Cancel + my bookings + polish. Share `@GrancviAppBot` with the first live master for A/B comparison with the old bot.

---

## Self-Review Checklist

- [ ] Backend reuses existing services/repositories — no business logic duplicated
- [ ] All endpoints require valid initData (no public booking API leak)
- [ ] CORS restricted
- [ ] App bot doesn't talk to masters — master notifications go via original `@GrancviBot` to preserve the single notification channel
- [ ] Frontend has zero business logic — all state derived from API
- [ ] Old bot unchanged and unaffected
- [ ] Deploy leaves old `@GrancviBot` service untouched in `docker-compose.prod.yml`

---

**Plan complete.**
