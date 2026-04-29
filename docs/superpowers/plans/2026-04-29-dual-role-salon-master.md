# Dual-Role: Salon Owner + Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Allow one Telegram account (`tg_id`) to be both a salon owner and a master simultaneously. Adds a tiny role-toggle to TMA header for dual-role users; single-role users see no UI changes.

**Architecture:** Drop the cross-role 409 in registration. Auto-link `Master.salon_id = Salon.id` for dual-role on registration. Extend `/v1/me` to return both profiles. TMA `RoleRouter` reads `localStorage.activeRole` to pick which dashboard to show.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / pytest; React + react-router-dom + TanStack Query / Vite / Tailwind.

**Spec:** `docs/superpowers/specs/2026-04-29-dual-role-salon-master-design.md`

---

## File Structure

### Backend (`tg-bot`, branch `feat/dual-role`)

| Файл | Действие |
|---|---|
| `src/api/routes/register.py` | Modify — убрать cross-role checks, auto-link salon_id |
| `src/api/schemas.py` | Modify — добавить `master_profile`/`salon_profile` в `MeOut` |
| `src/api/routes/me.py` | Modify — заполнять оба профиля |
| `tests/test_api_register.py` | Modify — добавить тесты на dual-role flow |
| `tests/test_api_me.py` | Modify (или create) — тест на dual-role response |

### Frontend (`grancvi-web`, branch `feat/onboarding-redesign` — добавляем поверх)

| Файл | Действие |
|---|---|
| `src/api/types.ts` | Modify — расширить `MeOut`, добавить `MeMasterProfileOut`, `MeSalonProfileOut` |
| `src/components/RoleToggle.tsx` | Create |
| `src/components/Layout.tsx` | Modify — встроить toggle в header (только для dual-role) |
| `src/App.tsx` | Modify — `RoleRouter` учитывает `localStorage.activeRole` |
| `src/pages/MasterDashboard.tsx` | Modify — добавить «+ Открыть свой салон» CTA если salon_profile отсутствует |
| `src/pages/SalonDashboard.tsx` | Modify — добавить «+ Я тоже мастер» CTA если master_profile отсутствует |
| `src/lib/i18n.ts` | Modify — новые ключи toggle/CTA |

---

## Phase 1 — Backend (`tg-bot`)

Branch: `feat/dual-role` from current `main` (which has `aeee5e2` HY confirm/reject). Auto-deploy on push to main.

### Task 1: Branch + baseline

- [ ] **Step 1: Switch to tg-bot, branch from main**

```bash
cd /Users/vanik/Desktop/projects/working-projects/tg-bot
git checkout main && git pull
git checkout -b feat/dual-role
docker compose up -d postgres redis
```

- [ ] **Step 2: Baseline tests**

```bash
SENTRY_DSN= uv run pytest tests/test_api_register.py tests/test_api_me.py tests/test_services_master_registration.py --tb=no -q
```
Expected: PASS.

---

### Task 2: Drop cross-role checks + auto-link salon_id

**Files:**
- Modify: `src/api/routes/register.py:148-152, 281-282`
- Tests: `tests/test_api_register.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api_register.py`:

```python
@pytest.mark.asyncio
async def test_register_master_self_succeeds_when_salon_exists(tg_user_headers, session) -> None:
    """Salon owner can register as master; master.salon_id auto-links to that salon."""
    from src.db.models import Master, Salon
    from sqlalchemy import select

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Step 1: register as salon
        salon_resp = await ac.post(
            "/v1/register/salon/self",
            headers=tg_user_headers,
            json={"name": "Dual Test Salon", "slug": "dual-test-salon"},
        )
        assert salon_resp.status_code == 201

        # Step 2: same tg_id registers as master — must succeed (was 409 before)
        master_resp = await ac.post(
            "/v1/register/master/self",
            headers=tg_user_headers,
            json={
                "name": "Dual Test Master",
                "specialty": "barber",
                "slug": "dual-test-master",
                "lang": "hy",
            },
        )
    assert master_resp.status_code == 201, master_resp.json()

    salon = await session.scalar(select(Salon).where(Salon.slug == "dual-test-salon"))
    master = await session.scalar(select(Master).where(Master.slug == "dual-test-master"))
    assert master is not None
    assert salon is not None
    assert master.salon_id == salon.id, "master.salon_id must auto-link to existing salon"


@pytest.mark.asyncio
async def test_register_salon_self_succeeds_when_master_exists(tg_user_headers, session) -> None:
    """Master can register as salon owner; master.salon_id back-fills."""
    from src.db.models import Master, Salon
    from sqlalchemy import select

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        master_resp = await ac.post(
            "/v1/register/master/self",
            headers=tg_user_headers,
            json={
                "name": "Solo Master",
                "specialty": "barber",
                "slug": "solo-master-x",
                "lang": "hy",
            },
        )
        assert master_resp.status_code == 201

        salon_resp = await ac.post(
            "/v1/register/salon/self",
            headers=tg_user_headers,
            json={"name": "My Salon", "slug": "my-salon-x"},
        )
    assert salon_resp.status_code == 201

    master = await session.scalar(select(Master).where(Master.slug == "solo-master-x"))
    salon = await session.scalar(select(Salon).where(Salon.slug == "my-salon-x"))
    assert master is not None
    assert salon is not None
    assert master.salon_id == salon.id, "existing master must auto-link to new salon"
```

- [ ] **Step 2: Run tests, confirm both fail**

```bash
SENTRY_DSN= uv run pytest tests/test_api_register.py::test_register_master_self_succeeds_when_salon_exists tests/test_api_register.py::test_register_salon_self_succeeds_when_master_exists -v
```
Expected: FAIL — current code returns 409.

- [ ] **Step 3: Modify `register_master_self` in `src/api/routes/register.py`**

Find:

```python
    if await session.scalar(select(Master).where(Master.tg_id == tg_id)):
        raise ApiError("already_registered", "already a master", status_code=409)
    if await session.scalar(select(Salon).where(Salon.owner_tg_id == tg_id)):
        raise ApiError("already_registered", "already a salon owner", status_code=409)
```

Replace with:

```python
    if await session.scalar(select(Master).where(Master.tg_id == tg_id)):
        raise ApiError("already_registered", "already a master", status_code=409)
    # Salon ownership is no longer mutually exclusive with master role —
    # a salon owner working in their own salon is a common case.
    existing_salon = await session.scalar(
        select(Salon).where(Salon.owner_tg_id == tg_id)
    )
```

Then after `master = await MasterRegistrationService(session).register_self(...)`, add:

```python
    # Auto-link to the salon the user already owns (if any) so the new
    # master shows up in the salon's catalog without a separate step.
    if existing_salon is not None:
        master.salon_id = existing_salon.id
```

- [ ] **Step 4: Modify `register_salon_self` symmetrically**

Find:

```python
    if await session.scalar(select(Salon).where(Salon.owner_tg_id == tg_id)):
        raise ApiError("already_registered", "already a salon owner", status_code=409)
    if await session.scalar(select(Master).where(Master.tg_id == tg_id)):
        raise ApiError("already_registered", "already a master", status_code=409)
```

Replace with:

```python
    if await session.scalar(select(Salon).where(Salon.owner_tg_id == tg_id)):
        raise ApiError("already_registered", "already a salon owner", status_code=409)
    # Master role is no longer mutually exclusive — capture the existing
    # master row so we can auto-link them to the new salon.
    existing_master = await session.scalar(
        select(Master).where(Master.tg_id == tg_id)
    )
```

Then after the salon row is created (after the `try/except IntegrityError`), add:

```python
    # Existing master self-registers a salon? Link the master to it so
    # they show up in their own salon's catalog automatically.
    if existing_master is not None:
        existing_master.salon_id = salon.id
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
SENTRY_DSN= uv run pytest tests/test_api_register.py -v
```

- [ ] **Step 6: Lint + types**

```bash
uv run ruff check src/api/routes/register.py tests/test_api_register.py
uv run ruff format src/api/routes/register.py tests/test_api_register.py
uv run mypy src/api/routes/register.py
```

- [ ] **Step 7: Commit**

```bash
git add src/api/routes/register.py tests/test_api_register.py
git commit -m "feat(register): allow salon owner + master dual-role on same tg_id"
```

---

### Task 3: Extend `MeOut` with both profiles

**Files:**
- Modify: `src/api/schemas.py` (find `class MeOut`)
- Modify: `src/api/routes/me.py`
- Tests: `tests/test_api_me.py`

- [ ] **Step 1: Inspect existing `MeOut` and `MeProfileOut` in `src/api/schemas.py`**

Read the current shape; note all fields. There's likely a `MeProfileOut` with `tg_id`, `first_name`, `master_id`, `master_name`, `slug`, `specialty`. We'll reuse parts.

- [ ] **Step 2: Add new schemas**

After `MeProfileOut` definition in `src/api/schemas.py`, add:

```python
class MeMasterProfileOut(BaseModel):
    master_id: UUID
    name: str
    slug: str
    specialty: str | None = None
    is_public: bool


class MeSalonProfileOut(BaseModel):
    salon_id: UUID
    name: str
    slug: str
    is_public: bool
```

If `UUID` isn't already imported there, add `from uuid import UUID`.

- [ ] **Step 3: Extend `MeOut`**

```python
class MeOut(BaseModel):
    role: Literal["master", "salon_owner", "client"]
    profile: MeProfileOut
    master_profile: MeMasterProfileOut | None = None
    salon_profile: MeSalonProfileOut | None = None
    is_admin: bool
    onboarded: bool | None = None
```

- [ ] **Step 4: Update `src/api/routes/me.py`**

Find the function that builds `MeOut`. Before returning, look up Master AND Salon for the same `tg_id`:

```python
    master = await session.scalar(select(Master).where(Master.tg_id == tg_id))
    salon = await session.scalar(select(Salon).where(Salon.owner_tg_id == tg_id))

    master_profile = (
        MeMasterProfileOut(
            master_id=master.id,
            name=master.name,
            slug=master.slug,
            specialty=master.specialty_text or None,
            is_public=master.is_public,
        )
        if master is not None
        else None
    )
    salon_profile = (
        MeSalonProfileOut(
            salon_id=salon.id,
            name=salon.name,
            slug=salon.slug,
            is_public=salon.is_public,
        )
        if salon is not None
        else None
    )

    # Primary role: master wins if both exist (more frequent interaction)
    if master is not None:
        role = "master"
    elif salon is not None:
        role = "salon_owner"
    else:
        role = "client"
```

Adjust based on existing structure of the function — the lookups may already exist (split between two if-branches). Refactor to do both queries up-front, so dual-role works.

`profile` field stays for backwards-compat — render it from whichever role is primary.

- [ ] **Step 5: Write a dual-role test**

In `tests/test_api_me.py` (create file if it doesn't exist; use existing pattern from `test_api_master.py`):

```python
@pytest.mark.asyncio
async def test_me_returns_both_profiles_when_dual_role(tg_user_headers, session) -> None:
    """Dual-role user gets both master_profile and salon_profile populated."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post(
            "/v1/register/salon/self",
            headers=tg_user_headers,
            json={"name": "DR Salon", "slug": "dr-salon"},
        )
        await ac.post(
            "/v1/register/master/self",
            headers=tg_user_headers,
            json={
                "name": "DR Master",
                "specialty": "barber",
                "slug": "dr-master",
                "lang": "hy",
            },
        )
        me_resp = await ac.get("/v1/me", headers=tg_user_headers)

    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["role"] == "master"  # primary
    assert body["master_profile"] is not None
    assert body["master_profile"]["slug"] == "dr-master"
    assert body["salon_profile"] is not None
    assert body["salon_profile"]["slug"] == "dr-salon"
```

- [ ] **Step 6: Run + lint**

```bash
SENTRY_DSN= uv run pytest tests/test_api_me.py tests/test_api_register.py -v
uv run ruff check src/api/schemas.py src/api/routes/me.py tests/test_api_me.py
uv run mypy src/api/schemas.py src/api/routes/me.py
```

- [ ] **Step 7: Commit**

```bash
git add src/api/schemas.py src/api/routes/me.py tests/test_api_me.py
git commit -m "feat(me): expose master_profile + salon_profile on dual-role"
```

---

### Task 4: Phase 1 final + push

- [ ] **Step 1: Full pytest sweep**

```bash
SENTRY_DSN= uv run pytest --tb=no -q | tail -5
```

- [ ] **Step 2: Lint everything**

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src/
```

- [ ] **Step 3: Merge to main + push (auto-deploy)**

```bash
git checkout main
git merge --no-ff feat/dual-role -m "Merge: dual-role salon + master on same tg_id"
git push origin main
```

- [ ] **Step 4: Wait for CI + deploy**

Poll via:
```bash
curl -s "https://api.github.com/repos/VanikVardanyan/grancvi/actions/runs?branch=main&per_page=2" | python3 -c "import json,sys; print(json.load(sys.stdin)['workflow_runs'][0]['status'])"
```

---

## Phase 2 — Frontend (`grancvi-web`)

Branch: keep working on `feat/onboarding-redesign` (no remote, local commits, scp deploy).

### Task 5: Update types in `src/api/types.ts`

**Files:**
- Modify: `src/api/types.ts`

- [ ] **Step 1: Find `MeOut` and `MeProfileOut`**

Read current shape.

- [ ] **Step 2: Add new types and extend `MeOut`**

After `MeProfileOut`, add:

```typescript
export type MeMasterProfileOut = {
  master_id: string;
  name: string;
  slug: string;
  specialty: string | null;
  is_public: boolean;
};

export type MeSalonProfileOut = {
  salon_id: string;
  name: string;
  slug: string;
  is_public: boolean;
};
```

Then extend `MeOut`:

```typescript
export type MeOut = {
  role: "master" | "salon_owner" | "client";
  profile: MeProfileOut;
  master_profile: MeMasterProfileOut | null;
  salon_profile: MeSalonProfileOut | null;
  is_admin: boolean;
  onboarded: boolean | null;
};
```

(Keep existing fields, just add `master_profile` and `salon_profile`.)

- [ ] **Step 3: Compile**

```bash
cd /Users/vanik/Desktop/projects/working-projects/grancvi-web
pnpm exec tsc -b --noEmit
```

If anything errors due to consumers expecting non-nullable — make them `| null` defaults.

- [ ] **Step 4: Commit**

```bash
git add src/api/types.ts
git commit -m "feat(types): add master_profile + salon_profile to MeOut"
```

---

### Task 6: Add i18n keys + RoleToggle component

**Files:**
- Modify: `src/lib/i18n.ts`
- Create: `src/components/RoleToggle.tsx`

- [ ] **Step 1: Add i18n keys**

In `src/lib/i18n.ts`, add to the `dict` object:

```typescript
  role_toggle_master: { ru: "Мастер", hy: "Վարպետ" },
  role_toggle_salon: { ru: "Салон", hy: "Սրահ" },
  cta_become_master: { ru: "+ Я тоже мастер", hy: "+ Ես նաև վարպետ եմ" },
  cta_open_salon: { ru: "+ Открыть свой салон", hy: "+ Բացել իմ սրահը" },
```

- [ ] **Step 2: Create RoleToggle**

`src/components/RoleToggle.tsx`:

```typescript
import { useNavigate } from "react-router-dom";

import { useLang } from "../lib/i18n";

const ACTIVE_ROLE_KEY = "grancvi.activeRole";

export function getActiveRole(): "master" | "salon" {
  try {
    const v = localStorage.getItem(ACTIVE_ROLE_KEY);
    if (v === "salon") return "salon";
  } catch {
    /* ignore */
  }
  return "master";
}

function setActiveRole(role: "master" | "salon"): void {
  try {
    localStorage.setItem(ACTIVE_ROLE_KEY, role);
  } catch {
    /* ignore */
  }
}

/**
 * Two-pill toggle for users who are both a master AND a salon owner.
 * Caller is responsible for only mounting it when both profiles exist.
 */
export function RoleToggle() {
  const { t } = useLang();
  const navigate = useNavigate();
  const active = getActiveRole();

  function pick(role: "master" | "salon") {
    if (role === active) return;
    setActiveRole(role);
    navigate("/", { replace: true });
  }

  return (
    <div className="flex bg-tg-secondary-bg rounded-full p-0.5 text-[11px] font-semibold">
      <button
        type="button"
        onClick={() => pick("master")}
        className={`rounded-full px-2.5 py-1 transition ${
          active === "master" ? "bg-tg-button text-tg-button-text" : "text-tg-hint"
        }`}
      >
        {t("role_toggle_master")}
      </button>
      <button
        type="button"
        onClick={() => pick("salon")}
        className={`rounded-full px-2.5 py-1 transition ${
          active === "salon" ? "bg-tg-button text-tg-button-text" : "text-tg-hint"
        }`}
      >
        {t("role_toggle_salon")}
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Compile**

```bash
pnpm exec tsc -b --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add src/lib/i18n.ts src/components/RoleToggle.tsx
git commit -m "feat(roles): RoleToggle component + i18n keys"
```

---

### Task 7: Wire RoleToggle in Layout (only when dual-role)

**Files:**
- Modify: `src/components/Layout.tsx`

- [ ] **Step 1: Find header in Layout.tsx**

Read existing structure.

- [ ] **Step 2: Add useMe + RoleToggle conditional**

At the top of `Layout`:

```typescript
import { useMe } from "../api/hooks";
import { RoleToggle } from "./RoleToggle";
```

Inside the component, before the return:

```typescript
const me = useMe();
const dualRole = !!(me.data?.master_profile && me.data?.salon_profile);
```

In the header JSX (where there's `<header>...</header>`), add `<RoleToggle />` near the title — typically right side. If header has flex layout, use `ml-auto` or place inside the right-aligned group. Concrete spot: after the title-text div, add:

```tsx
{dualRole && <RoleToggle />}
```

The exact placement depends on existing markup — pick a spot that's visible without crowding.

- [ ] **Step 3: Compile**

```bash
pnpm exec tsc -b --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add src/components/Layout.tsx
git commit -m "feat(layout): mount RoleToggle for dual-role users"
```

---

### Task 8: RoleRouter — read activeRole

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: Find the master/salon_owner branches in `RoleRouter`**

Around lines 95-115 (current state):

```typescript
  if (me.data?.role === "salon_owner") {
    return <SalonDashboard />;
  }
  if (me.data?.role === "master") {
    return <MasterDashboard name={me.data.profile.master_name ?? "Master"} />;
  }
```

- [ ] **Step 2: Replace with dual-role aware logic**

```typescript
  // Dual-role users (have both master + salon profiles) honor a
  // localStorage toggle to pick which dashboard to show. Single-role
  // users just follow `me.role` as before.
  const hasMaster = !!me.data?.master_profile;
  const hasSalon = !!me.data?.salon_profile;
  if (hasMaster && hasSalon) {
    const active = getActiveRole();
    if (active === "salon") return <SalonDashboard />;
    return <MasterDashboard name={me.data.profile.master_name ?? "Master"} />;
  }
  if (me.data?.role === "salon_owner") {
    return <SalonDashboard />;
  }
  if (me.data?.role === "master") {
    return <MasterDashboard name={me.data.profile.master_name ?? "Master"} />;
  }
```

Add import at top:

```typescript
import { getActiveRole } from "./components/RoleToggle";
```

- [ ] **Step 3: Compile**

```bash
pnpm exec tsc -b --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add src/App.tsx
git commit -m "feat(router): dual-role users pick dashboard via activeRole toggle"
```

---

### Task 9: CTA buttons in dashboards

**Files:**
- Modify: `src/pages/SalonDashboard.tsx`
- Modify: `src/pages/MasterDashboard.tsx`

- [ ] **Step 1: SalonDashboard — add «+ Я тоже мастер»**

In `src/pages/SalonDashboard.tsx`, add at top:

```typescript
import { Link } from "react-router-dom";
import { useMe } from "../api/hooks";
```

Inside the component, near the page bottom (or in a sensible spot near other action items), add:

```tsx
{!me.data?.master_profile && (
  <Link
    to="/register/self"
    className="inline-block w-full text-center rounded-xl bg-white/60 dark:bg-white/5 border border-black/5 dark:border-white/10 px-4 py-3 text-sm font-medium active:opacity-70"
  >
    {t("cta_become_master")}
  </Link>
)}
```

Reuse existing `useMe()` if already in file; if not, add the import + `const me = useMe();`.

- [ ] **Step 2: MasterDashboard — add «+ Открыть свой салон»**

Same pattern in `src/pages/MasterDashboard.tsx`:

```tsx
{!me.data?.salon_profile && (
  <Link
    to="/register/self-salon"
    className="inline-block w-full text-center rounded-xl bg-white/60 dark:bg-white/5 border border-black/5 dark:border-white/10 px-4 py-3 text-sm font-medium active:opacity-70"
  >
    {t("cta_open_salon")}
  </Link>
)}
```

Note: this is a **soft** CTA — it appears as a small link in the dashboard, not a primary button. Don't push it on every existing master.

- [ ] **Step 3: Compile**

```bash
pnpm exec tsc -b --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add src/pages/SalonDashboard.tsx src/pages/MasterDashboard.tsx
git commit -m "feat(dashboards): cross-role CTAs (become master / open salon)"
```

---

### Task 10: Build + scp deploy

- [ ] **Step 1: Build**

```bash
cd /Users/vanik/Desktop/projects/working-projects/grancvi-web
pnpm build
```

Expected: clean.

- [ ] **Step 2: ESLint sanity (only check our changed files)**

```bash
pnpm exec eslint src/components/RoleToggle.tsx src/components/Layout.tsx src/App.tsx src/pages/SalonDashboard.tsx src/pages/MasterDashboard.tsx src/lib/i18n.ts src/api/types.ts
```

- [ ] **Step 3: Deploy**

```bash
scp -i ~/.ssh/grancvi-deploy -r dist/* deploy@94.130.149.91:/var/www/jampord-app/
```

- [ ] **Step 4: Verify bundle live**

```bash
curl -s https://app.grancvi.am/ | grep -oE 'index-[^"]+\.js' | head -1
```

Compare with local `ls dist/assets/ | grep js`.

---

## Phase 3 — Smoke + cleanup

### Task 11: Prod smoke

- [ ] **Step 1: User test**

User registers as salon, then registers as master with same tg_id. Verifies:
- No 409 error
- Both profiles exist in DB
- TMA shows toggle in header
- Switching between Master/Salon works
- Master appears in salon's catalog

- [ ] **Step 2: If smoke passes — close out**

Mark Task 21 (the original onboarding) as fully complete.
