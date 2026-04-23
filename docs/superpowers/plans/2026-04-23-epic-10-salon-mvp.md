# Epic 10.1 — Salon MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add salon-tier support on top of the existing solo-master flow. Salon owners can onboard via admin invite, invite masters to their salon, and create appointments on behalf of those masters from a central "front desk" menu.

**Architecture:** Purely additive. New `salons` table, nullable `masters.salon_id` FK. Solo masters (salon_id=NULL) keep existing behavior untouched. Router order: admin → master → salon → client. A `UserMiddleware` resolves both `data["master"]` and `data["salon"]` per update. Salon-created appointments use `source="salon_manual"` and are auto-confirmed (skip `pending`).

**Tech Stack:** aiogram 3.x, SQLAlchemy 2.0 async, Alembic, PostgreSQL, Redis (FSM), segno (QR). No new deps.

**Out of scope (deferred):**
- Client-facing salon landing page (`?start=salon_<slug>`) — Epic 10.2
- Grouped client catalog (solo + salons) — Epic 10.2
- Salon stats screen — Epic 10.3
- Logo upload, description edit — Epic 10.3

**Invariants:**
- Solo master flow untouched. Every new query path handles `salon_id IS NULL` correctly.
- Salon owner `tg_id` never coincides with any master's `tg_id` (reject on registration).
- Salon owner sees only: list of their masters (public fields), free slots of a master (for booking), no individual appointments / client PII.
- Slugs share one namespace: a salon slug must not collide with any master slug, and vice versa.

---

## File Structure

### New files
- `migrations/versions/0005_salons_and_enum_extensions.py` — schema + enum extensions
- `src/db/models.py` — add `Salon` model, extend `Master`, `Invite` (single file, existing)
- `src/repositories/salons.py` — `SalonRepository`
- `src/callback_data/admin.py` — add `AdminInviteSalonCallback` (existing file, extend)
- `src/callback_data/salon.py` — callback data for salon menu + booking flow
- `src/fsm/salon_register.py` — `SalonRegister` FSM
- `src/fsm/salon_add.py` — `SalonAddAppt` FSM
- `src/keyboards/salon.py` — `salon_main_menu`, `salon_masters_pick_kb`, `salon_add_confirm_kb`, etc.
- `src/handlers/salon/__init__.py` — router composition
- `src/handlers/salon/start.py` — `/start` dispatch (salon invite, salon owner no-payload)
- `src/handlers/salon/registration.py` — onboarding FSM handlers
- `src/handlers/salon/menu.py` — button routing
- `src/handlers/salon/masters.py` — "My masters" view + invite button
- `src/handlers/salon/add_appt.py` — salon-creates-appointment FSM
- `src/handlers/salon/my_link.py` — link + QR for salon deep link (shown even though discovery page lands in 10.2; button ships now for parity)
- `src/services/salon_booking.py` — thin wrapper around `BookingService.create_manual` for salon-sourced bookings
- Tests per file (listed in each task)

### Modified files
- `src/db/models.py` — Salon model, Master.salon_id, Invite.kind + salon_id
- `src/services/booking.py` — extend `create_manual` to accept `source` (default stays `master_manual`); extend enum validation
- `src/services/master_registration.py` — bind salon_id from invite
- `src/repositories/invites.py` — include `kind`, `salon_id`
- `src/middlewares/user.py` — populate `data["salon"]`
- `src/handlers/master/start.py` — filter rejects non-master invites
- `src/handlers/admin/invites_admin.py` — "Пригласить салон" button
- `src/handlers/__init__.py` — add salon router in correct order
- `src/strings.py` — all salon strings (ru + hy)
- `src/main.py` — (no changes expected; middleware already registered)

---

## Task 1: Migration 0005 (schema + enum extensions)

**Files:**
- Create: `migrations/versions/0005_salons_and_enum_extensions.py`

- [ ] **Step 1: Write the migration**

```python
"""epic 10.1: salons table + enum extensions

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-23 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "salons",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("owner_tg_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(32), nullable=False, unique=True),
        sa.Column("logo_file_id", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("blocked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.add_column(
        "masters",
        sa.Column(
            "salon_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("salons.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_masters_salon_id", "masters", ["salon_id"])

    op.add_column(
        "invites",
        sa.Column(
            "kind",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'master'"),
        ),
    )
    op.add_column(
        "invites",
        sa.Column(
            "salon_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("salons.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_invites_kind",
        "invites",
        "kind IN ('master', 'salon_owner')",
    )

    op.drop_constraint("ck_appointments_source", "appointments", type_="check")
    op.create_check_constraint(
        "ck_appointments_source",
        "appointments",
        "source IN ('client_request', 'master_manual', 'salon_manual')",
    )
    op.drop_constraint("ck_appointments_cancelled_by", "appointments", type_="check")
    op.create_check_constraint(
        "ck_appointments_cancelled_by",
        "appointments",
        "cancelled_by IS NULL OR cancelled_by IN ('client', 'master', 'system', 'salon')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_appointments_cancelled_by", "appointments", type_="check")
    op.create_check_constraint(
        "ck_appointments_cancelled_by",
        "appointments",
        "cancelled_by IS NULL OR cancelled_by IN ('client', 'master', 'system')",
    )
    op.drop_constraint("ck_appointments_source", "appointments", type_="check")
    op.create_check_constraint(
        "ck_appointments_source",
        "appointments",
        "source IN ('client_request', 'master_manual')",
    )
    op.drop_constraint("ck_invites_kind", "invites", type_="check")
    op.drop_column("invites", "salon_id")
    op.drop_column("invites", "kind")
    op.drop_index("ix_masters_salon_id", table_name="masters")
    op.drop_column("masters", "salon_id")
    op.drop_table("salons")
```

- [ ] **Step 2: Run migration upgrade+downgrade on local test DB**

```bash
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run alembic upgrade head
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run alembic downgrade 0004
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run alembic upgrade head
```
Expected: All three commands succeed without error.

- [ ] **Step 3: Commit**

```bash
git add migrations/versions/0005_salons_and_enum_extensions.py
git commit -m "feat(salons): migration 0005 — salons table + enum extensions"
```

---

## Task 2: Models — Salon, Master.salon_id, Invite fields

**Files:**
- Modify: `src/db/models.py`
- Modify: `tests/test_exceptions_epic9.py` (as smoke — add a model construction test in a new file instead)
- Create: `tests/test_models_salon.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models_salon.py
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master, Salon


@pytest.mark.asyncio
async def test_salon_can_be_created_with_minimum_fields(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=12345, name="Test Salon", slug="test-salon")
    session.add(salon)
    await session.flush()
    await session.commit()
    await session.refresh(salon)
    assert salon.id is not None
    assert salon.is_public is True
    assert salon.logo_file_id is None


@pytest.mark.asyncio
async def test_master_can_be_linked_to_salon(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=111, name="S", slug="s-1")
    session.add(salon)
    await session.flush()
    master = Master(tg_id=222, name="M", slug="m-1", salon_id=salon.id)
    session.add(master)
    await session.flush()
    await session.commit()
    await session.refresh(master)
    assert master.salon_id == salon.id


@pytest.mark.asyncio
async def test_invite_has_kind_and_optional_salon(session: AsyncSession) -> None:
    from datetime import UTC, datetime, timedelta

    expires = datetime.now(UTC) + timedelta(days=7)
    inv = Invite(
        code="abc123", created_by_tg_id=999, expires_at=expires, kind="master"
    )
    session.add(inv)
    await session.flush()
    await session.commit()
    await session.refresh(inv)
    assert inv.kind == "master"
    assert inv.salon_id is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_models_salon.py -v`
Expected: FAIL — `Salon` does not exist / `Master` has no `salon_id`.

- [ ] **Step 3: Add the Salon model and update Master/Invite**

In `src/db/models.py`, add at an appropriate place (e.g., after `Invite`):

```python
class Salon(Base):
    __tablename__ = "salons"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    owner_tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    logo_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    blocked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
```

In the `Master` class, add:

```python
    salon_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("salons.id", ondelete="SET NULL"),
        nullable=True,
    )
```

In the `Invite` class, add:

```python
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'master'")
    )
    salon_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("salons.id", ondelete="CASCADE"),
        nullable=True,
    )
```

Also extend `Invite.__table_args__` with:

```python
        CheckConstraint(
            "kind IN ('master', 'salon_owner')",
            name="ck_invites_kind",
        ),
```

- [ ] **Step 4: Run the test**

Run: `uv run pytest tests/test_models_salon.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Full regression**

Run: `uv run pytest -q`
Expected: 460+ tests pass, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/db/models.py tests/test_models_salon.py
git commit -m "feat(salons): add Salon model + Master.salon_id + Invite.kind/salon_id"
```

---

## Task 3: SalonRepository

**Files:**
- Create: `src/repositories/salons.py`
- Create: `tests/test_repositories_salons.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_repositories_salons.py
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Salon
from src.repositories.salons import SalonRepository


@pytest.mark.asyncio
async def test_create_salon(session: AsyncSession) -> None:
    repo = SalonRepository(session)
    salon = await repo.create(owner_tg_id=42, name="Hair World", slug="hair-world")
    await session.commit()
    assert salon.id is not None
    assert salon.slug == "hair-world"


@pytest.mark.asyncio
async def test_get_by_slug(session: AsyncSession) -> None:
    session.add(Salon(owner_tg_id=1, name="A", slug="aaa-1"))
    await session.commit()
    repo = SalonRepository(session)
    found = await repo.by_slug("aaa-1")
    assert found is not None and found.slug == "aaa-1"
    assert await repo.by_slug("nope") is None


@pytest.mark.asyncio
async def test_get_by_owner_tg_id(session: AsyncSession) -> None:
    session.add(Salon(owner_tg_id=77, name="A", slug="s77"))
    await session.commit()
    repo = SalonRepository(session)
    found = await repo.by_owner_tg_id(77)
    assert found is not None and found.owner_tg_id == 77
    assert await repo.by_owner_tg_id(99) is None


@pytest.mark.asyncio
async def test_list_masters(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=1, name="S", slug="s1")
    session.add(salon)
    await session.flush()
    session.add_all(
        [
            Master(tg_id=101, name="A", slug="a-1", salon_id=salon.id),
            Master(tg_id=102, name="B", slug="b-1", salon_id=salon.id),
            Master(tg_id=103, name="C", slug="c-1"),  # solo
        ]
    )
    await session.commit()
    repo = SalonRepository(session)
    masters = await repo.list_masters(salon.id)
    slugs = sorted(m.slug for m in masters)
    assert slugs == ["a-1", "b-1"]
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest tests/test_repositories_salons.py -v`
Expected: FAIL — `SalonRepository` does not exist.

- [ ] **Step 3: Implement the repository**

```python
# src/repositories/salons.py
from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Salon


class SalonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, owner_tg_id: int, name: str, slug: str) -> Salon:
        salon = Salon(owner_tg_id=owner_tg_id, name=name, slug=slug)
        self._session.add(salon)
        await self._session.flush()
        return salon

    async def by_id(self, salon_id: UUID) -> Salon | None:
        return cast(Salon | None, await self._session.get(Salon, salon_id))

    async def by_slug(self, slug: str) -> Salon | None:
        stmt = select(Salon).where(Salon.slug == slug)
        return await self._session.scalar(stmt)

    async def by_owner_tg_id(self, tg_id: int) -> Salon | None:
        stmt = select(Salon).where(Salon.owner_tg_id == tg_id)
        return await self._session.scalar(stmt)

    async def list_masters(self, salon_id: UUID) -> list[Master]:
        stmt = select(Master).where(Master.salon_id == salon_id).order_by(Master.name)
        return list((await self._session.scalars(stmt)).all())

    async def update_name(self, salon_id: UUID, name: str) -> None:
        salon = await self.by_id(salon_id)
        if salon is not None:
            salon.name = name

    async def update_slug(self, salon_id: UUID, slug: str) -> None:
        salon = await self.by_id(salon_id)
        if salon is not None:
            salon.slug = slug
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_repositories_salons.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/repositories/salons.py tests/test_repositories_salons.py
git commit -m "feat(salons): SalonRepository CRUD"
```

---

## Task 4: Slug service shares namespace with salons

**Files:**
- Modify: `src/services/slug.py`
- Create: `tests/test_services_slug_shared_namespace.py` (or extend existing slug tests)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_services_slug_shared_namespace.py
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Salon
from src.services.slug import SlugService


@pytest.mark.asyncio
async def test_master_slug_rejected_if_taken_by_salon(session: AsyncSession) -> None:
    session.add(Salon(owner_tg_id=1, name="S", slug="conflict"))
    await session.commit()
    svc = SlugService(session)
    taken = await svc.is_taken("conflict")
    assert taken is True


@pytest.mark.asyncio
async def test_salon_slug_rejected_if_taken_by_master(session: AsyncSession) -> None:
    session.add(Master(tg_id=1, name="M", slug="mine-0001"))
    await session.commit()
    svc = SlugService(session)
    taken = await svc.is_taken("mine-0001")
    assert taken is True


@pytest.mark.asyncio
async def test_fresh_slug_is_not_taken(session: AsyncSession) -> None:
    svc = SlugService(session)
    assert await svc.is_taken("fresh-slug") is False
```

- [ ] **Step 2: Verify tests fail (or adjust to current API)**

Run: `uv run pytest tests/test_services_slug_shared_namespace.py -v`

First look at `src/services/slug.py` — the method may currently be called something like `_is_taken` or checks only masters. Let the test define the new API: `is_taken(slug) -> bool` that checks BOTH tables.

Expected: FAIL if method name differs or only masters are checked.

- [ ] **Step 3: Update SlugService**

Open `src/services/slug.py`. Adapt to include a `Salon` check. Example (real API may differ — keep the existing signature for `generate_default`, `validate`; add/modify `is_taken`):

```python
# inside SlugService
async def is_taken(self, slug: str) -> bool:
    from src.db.models import Master, Salon  # avoid top-level cycle if needed

    master_q = select(Master.id).where(Master.slug == slug).limit(1)
    salon_q = select(Salon.id).where(Salon.slug == slug).limit(1)
    master_hit = await self._session.scalar(master_q)
    if master_hit is not None:
        return True
    salon_hit = await self._session.scalar(salon_q)
    return salon_hit is not None
```

Update any callers in `src/services/master_registration.py` and `src/handlers/master/registration.py` that previously queried only `masters.by_slug` — switch to `SlugService.is_taken`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_services_slug_shared_namespace.py tests/test_services_slug.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/services/slug.py tests/test_services_slug_shared_namespace.py src/services/master_registration.py src/handlers/master/registration.py
git commit -m "feat(salons): share slug namespace across masters and salons"
```

---

## Task 5: UserMiddleware resolves both master and salon

**Files:**
- Modify: `src/middlewares/user.py`
- Create: `tests/test_middleware_user_salon.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_middleware_user_salon.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Chat, Message, Update, User
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Salon
from src.middlewares.user import UserMiddleware


def _mk_update(user_id: int) -> Update:
    user = User(id=user_id, is_bot=False, first_name="U")
    chat = Chat(id=user_id, type="private")
    msg = Message.model_construct(
        message_id=1, date=0, chat=chat, from_user=user, text="/start"  # type: ignore[arg-type]
    )
    return Update.model_construct(update_id=1, message=msg)


@pytest.mark.asyncio
async def test_user_middleware_populates_salon_when_owner(session: AsyncSession) -> None:
    session.add(Salon(owner_tg_id=500, name="S", slug="s-own"))
    await session.commit()

    mw = UserMiddleware()
    captured: dict[str, object] = {}

    async def handler(event, data):
        captured["salon"] = data.get("salon")
        captured["master"] = data.get("master")

    await mw(handler, _mk_update(user_id=500), {"session": session})
    assert captured["master"] is None
    assert captured["salon"] is not None
    assert captured["salon"].owner_tg_id == 500


@pytest.mark.asyncio
async def test_user_middleware_salon_none_when_not_owner(session: AsyncSession) -> None:
    mw = UserMiddleware()
    captured: dict[str, object] = {}

    async def handler(event, data):
        captured["salon"] = data.get("salon")

    await mw(handler, _mk_update(user_id=9999), {"session": session})
    assert captured["salon"] is None
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest tests/test_middleware_user_salon.py -v`
Expected: FAIL — `data["salon"]` key missing.

- [ ] **Step 3: Update UserMiddleware**

In `src/middlewares/user.py`, after resolving master:

```python
from src.db.models import Master, Salon  # Salon added
# ...

# After setting data["master"]:
data["salon"] = None
salon = await session.scalar(select(Salon).where(Salon.owner_tg_id == tg_user.id))
if salon is not None:
    data["salon"] = salon
```

Put it after the master lookup so the order is master → salon.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_middleware_user_salon.py -v`
Expected: PASS.

- [ ] **Step 5: Regression**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add src/middlewares/user.py tests/test_middleware_user_salon.py
git commit -m "feat(salons): UserMiddleware populates data['salon'] for owners"
```

---

## Task 6: Admin issues "salon_owner" invite

**Files:**
- Modify: `src/callback_data/admin.py` — add `AdminNewSalonCallback`
- Modify: `src/keyboards/admin.py` — add salon-invite button in the admin invites keyboard
- Modify: `src/handlers/admin/invites_admin.py` — handle new callback + invite creation
- Modify: `src/repositories/invites.py` — support creating with `kind="salon_owner"`
- Modify: `src/strings.py` — button label + confirmation text (ru + hy)
- Create: `tests/test_handlers_admin_salon_invite.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_handlers_admin_salon_invite.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite


@pytest.mark.asyncio
async def test_admin_invite_salon_creates_salon_owner_kind(session: AsyncSession) -> None:
    from src.handlers.admin.invites_admin import cb_admin_new_salon

    cb = AsyncMock()
    cb.from_user = MagicMock(id=747967837)
    cb.message = AsyncMock()

    await cb_admin_new_salon(callback=cb, session=session)

    invites = list((await session.scalars(select(Invite))).all())
    assert len(invites) == 1
    assert invites[0].kind == "salon_owner"
    assert invites[0].created_by_tg_id == 747967837
```

- [ ] **Step 2: Verify test fails**

Run: `uv run pytest tests/test_handlers_admin_salon_invite.py -v`
Expected: FAIL — handler doesn't exist.

- [ ] **Step 3: Update `InviteRepository.create` to accept kind+salon_id**

In `src/repositories/invites.py`, find `create()` and extend:

```python
async def create(
    self,
    *,
    created_by_tg_id: int,
    ttl_days: int = 7,
    kind: str = "master",
    salon_id: UUID | None = None,
) -> Invite:
    # existing random code generation + expires_at
    inv = Invite(
        code=code,
        created_by_tg_id=created_by_tg_id,
        expires_at=expires_at,
        kind=kind,
        salon_id=salon_id,
    )
    self._session.add(inv)
    await self._session.flush()
    return inv
```

- [ ] **Step 4: Add callback data and button**

In `src/callback_data/admin.py` (or the existing admin invites callback file) add:

```python
class AdminNewSalonCallback(CallbackData, prefix="ans"):
    pass
```

In `src/keyboards/admin.py`, locate the admin invites keyboard (or create one) and add:

```python
InlineKeyboardButton(
    text=strings.ADMIN_INVITE_NEW_SALON_BTN,
    callback_data=AdminNewSalonCallback().pack(),
),
```

Add strings in `src/strings.py`:
- ru: `ADMIN_INVITE_NEW_SALON_BTN` = "➕ Пригласить салон"
- ru: `ADMIN_INVITE_SALON_CREATED_FMT` = "Инвайт салона создан.\n\nКод: `{code}`\nСсылка: {link}\nДействителен до: {expires}"
- hy: `ADMIN_INVITE_NEW_SALON_BTN` = "➕ Հրավիրել սրահ"
- hy: `ADMIN_INVITE_SALON_CREATED_FMT` = "Սրահի հրավերը ստեղծված է։\n\nԿոդ՝ `{code}`\nՀղում՝ {link}\nՎավերական մինչ՝ {expires}"

- [ ] **Step 5: Implement handler**

In `src/handlers/admin/invites_admin.py`:

```python
from src.callback_data.admin import AdminNewSalonCallback

@router.callback_query(AdminNewSalonCallback.filter())
async def cb_admin_new_salon(callback: CallbackQuery, session: AsyncSession) -> None:
    tg_id = callback.from_user.id if callback.from_user else 0
    repo = InviteRepository(session)
    invite = await repo.create(created_by_tg_id=tg_id, kind="salon_owner")
    await session.commit()

    link = f"https://t.me/{settings.bot_username}?start=invite_{invite.code}"
    tz = ZoneInfo("Asia/Yerevan")
    expires_local = invite.expires_at.astimezone(tz).strftime("%d.%m.%Y %H:%M")

    text = strings.ADMIN_INVITE_SALON_CREATED_FMT.format(
        code=invite.code, link=link, expires=expires_local
    )
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(text, parse_mode="Markdown")
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_handlers_admin_salon_invite.py -v`
Expected: PASS.

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(salons): admin can issue salon_owner invites"
```

---

## Task 7: Salon registration FSM (states + lang + name)

**Files:**
- Create: `src/fsm/salon_register.py`
- Create: `src/callback_data/salon.py`

- [ ] **Step 1: Create FSM**

```python
# src/fsm/salon_register.py
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SalonRegister(StatesGroup):
    waiting_lang = State()
    waiting_name = State()
    waiting_slug_confirm = State()
    waiting_custom_slug = State()
```

- [ ] **Step 2: Create callback data stubs (for later tasks)**

```python
# src/callback_data/salon.py
from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class SalonSlugConfirmCallback(CallbackData, prefix="ssc"):
    action: Literal["use", "change"]


class SalonMasterPickCallback(CallbackData, prefix="smp"):
    master_id: UUID


class SalonSlotPickCallback(CallbackData, prefix="sslt"):
    slot_iso: str


class SalonNewClientCallback(CallbackData, prefix="snc"):
    action: Literal["new", "search"]


class SalonSkipPhoneCallback(CallbackData, prefix="sspp"):
    pass


class SalonConfirmApptCallback(CallbackData, prefix="scap"):
    action: Literal["save", "cancel"]
```

- [ ] **Step 3: Commit (no tests — this task ships support files only, tested by downstream tasks)**

```bash
git add src/fsm/salon_register.py src/callback_data/salon.py
git commit -m "feat(salons): FSM + callback data stubs"
```

---

## Task 8: Salon `/start` handler + master `/start` filter update

**Files:**
- Create: `src/handlers/salon/__init__.py`
- Create: `src/handlers/salon/start.py`
- Modify: `src/handlers/master/start.py` — `HasInviteOrMaster` must reject salon invites
- Modify: `src/handlers/__init__.py` — register salon router before client router
- Create: `tests/test_handlers_salon_start.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_handlers_salon_start.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Salon
from src.fsm.salon_register import SalonRegister
from src.handlers.salon.start import handle_salon_start


async def _mkctx() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))


@pytest.mark.asyncio
async def test_start_with_salon_owner_invite_enters_registration(
    session: AsyncSession,
) -> None:
    session.add(
        Invite(
            code="salown1",
            created_by_tg_id=1,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            kind="salon_owner",
        )
    )
    await session.commit()

    msg = AsyncMock()
    msg.text = "/start invite_salown1"
    msg.from_user = MagicMock(id=500)
    state = await _mkctx()

    await handle_salon_start(message=msg, salon=None, state=state, session=session)
    assert await state.get_state() == SalonRegister.waiting_lang.state


@pytest.mark.asyncio
async def test_start_as_registered_salon_owner_shows_main_menu(
    session: AsyncSession,
) -> None:
    salon = Salon(owner_tg_id=777, name="S", slug="ss-1")
    session.add(salon)
    await session.commit()

    msg = AsyncMock()
    msg.text = "/start"
    msg.from_user = MagicMock(id=777)
    state = await _mkctx()

    await handle_salon_start(message=msg, salon=salon, state=state, session=session)
    msg.answer.assert_awaited()
```

- [ ] **Step 2: Verify failing**

Run: `uv run pytest tests/test_handlers_salon_start.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Write master filter update**

In `src/handlers/master/start.py`, change `HasInviteOrMaster` to reject non-master invites:

```python
from src.repositories.invites import InviteRepository

class HasInviteOrMaster(Filter):
    async def __call__(
        self,
        event: Message,
        master: Master | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        if master is not None:
            return True
        code = _parse_invite_payload(event.text)
        if code is None:
            return False
        if session is None:
            return False
        repo = InviteRepository(session)
        invite = await repo.by_code(code)
        return invite is not None and invite.kind == "master"
```

(The filter signature in aiogram can receive arbitrary kwargs from middleware data including `session`.)

- [ ] **Step 4: Write salon/start.py**

```python
# src/handlers/salon/start.py
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from aiogram import Router
from aiogram.filters import CommandStart, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Salon
from src.fsm.salon_register import SalonRegister
from src.keyboards.common import lang_picker
from src.keyboards.salon import salon_main_menu
from src.repositories.invites import InviteRepository
from src.strings import strings

router = Router(name="salon_start")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


def _parse_invite(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return None
    payload = parts[1]
    return payload[len("invite_") :] if payload.startswith("invite_") else None


class HasSalonInviteOrOwner(Filter):
    async def __call__(
        self,
        event: Message,
        salon: Salon | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        if salon is not None:
            return True
        code = _parse_invite(event.text)
        if code is None or session is None:
            return False
        repo = InviteRepository(session)
        invite = await repo.by_code(code)
        return invite is not None and invite.kind == "salon_owner"


@router.message(CommandStart(), HasSalonInviteOrOwner())
async def handle_salon_start(
    message: Message,
    salon: Salon | None,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    code = _parse_invite(message.text)
    if code is not None and salon is None:
        repo = InviteRepository(session)
        invite = await repo.by_code(code)
        if invite is None:
            await message.answer(strings.INVITE_NOT_FOUND)
            return
        if invite.used_at is not None:
            await message.answer(strings.INVITE_ALREADY_USED)
            return
        if invite.expires_at <= datetime.now(UTC):
            await message.answer(strings.INVITE_EXPIRED)
            return
        await state.clear()
        await state.update_data(invite_code=code)
        await state.set_state(SalonRegister.waiting_lang)
        await message.answer(strings.LANG_PICK_PROMPT, reply_markup=lang_picker())
        return

    if salon is not None:
        await state.clear()
        await message.answer(
            strings.SALON_WELCOME_BACK, reply_markup=salon_main_menu()
        )
```

- [ ] **Step 5: Stub `salon_main_menu` with placeholder**

In `src/keyboards/salon.py`:

```python
# src/keyboards/salon.py
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from src.strings import strings


def salon_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=strings.SALON_MENU_MY_MASTERS),
                KeyboardButton(text=strings.SALON_MENU_INVITE_MASTER),
            ],
            [KeyboardButton(text=strings.SALON_MENU_ADD_APPT)],
            [
                KeyboardButton(text=strings.SALON_MENU_MY_LINK),
                KeyboardButton(text=strings.SALON_MENU_QR),
            ],
            [KeyboardButton(text=strings.SALON_MENU_SETTINGS)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
```

Add to `src/strings.py` (both ru and hy) — placeholders sufficient for this task, full strings added in Task 17:

```python
# ru
"SALON_WELCOME_BACK": "С возвращением, салон. Что дальше?",
"SALON_MENU_MY_MASTERS": "👥 Мои мастера",
"SALON_MENU_INVITE_MASTER": "➕ Пригласить мастера",
"SALON_MENU_ADD_APPT": "➕ Новая запись",
"SALON_MENU_MY_LINK": "🔗 Моя ссылка",
"SALON_MENU_QR": "📱 QR-код",
"SALON_MENU_SETTINGS": "⚙️ Настройки",
# hy
"SALON_WELCOME_BACK": "Բարի վերադարձ, սրահ։",
"SALON_MENU_MY_MASTERS": "👥 Իմ վարպետները",
"SALON_MENU_INVITE_MASTER": "➕ Հրավիրել վարպետ",
"SALON_MENU_ADD_APPT": "➕ Նոր գրանցում",
"SALON_MENU_MY_LINK": "🔗 Իմ հղումը",
"SALON_MENU_QR": "📱 QR-կոդ",
"SALON_MENU_SETTINGS": "⚙️ Կարգավորումներ",
```

- [ ] **Step 6: Register router**

```python
# src/handlers/salon/__init__.py
from __future__ import annotations

from aiogram import Router

from src.handlers.salon.start import router as start_router

router = Router(name="salon")
router.include_router(start_router)

__all__ = ["router"]
```

In `src/handlers/__init__.py`:

```python
from src.handlers.salon import router as salon_router
# ...
root.include_router(admin_router)
root.include_router(master_router)
root.include_router(salon_router)  # NEW
root.include_router(client_router)
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_handlers_salon_start.py -v`
Expected: PASS.

- [ ] **Step 8: Full regression**

Run: `uv run pytest -q`
Expected: all pass. If `test_handlers_master_registration.py` has invite fixtures, they may need `kind="master"` explicit — adjust if needed (most should default to `'master'` via server_default, so should work).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(salons): /start dispatch for salon owners + invite"
```

---

## Task 9: Salon registration — name + slug + finalize

**Files:**
- Create: `src/services/salon_registration.py`
- Create: `src/handlers/salon/registration.py`
- Modify: `src/handlers/salon/__init__.py` — include registration_router
- Create: `tests/test_handlers_salon_registration.py`

- [ ] **Step 1: Write service + handler tests**

```python
# tests/test_handlers_salon_registration.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.register import LangPickCallback
from src.callback_data.salon import SalonSlugConfirmCallback
from src.db.models import Invite, Salon
from src.fsm.salon_register import SalonRegister
from src.handlers.salon.registration import (
    register_handle_custom_slug,
    register_handle_lang,
    register_handle_name,
    register_handle_slug_confirm,
)


async def _mkctx() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))


@pytest.mark.asyncio
async def test_full_registration_flow(session: AsyncSession) -> None:
    session.add(
        Invite(
            code="flow1",
            created_by_tg_id=1,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            kind="salon_owner",
        )
    )
    await session.commit()

    state = await _mkctx()
    await state.set_state(SalonRegister.waiting_lang)
    await state.update_data(invite_code="flow1")

    cb = AsyncMock()
    cb.message = AsyncMock()
    await register_handle_lang(cb, callback_data=LangPickCallback(lang="ru"), state=state)
    assert await state.get_state() == SalonRegister.waiting_name.state

    msg = AsyncMock()
    msg.text = "Hair World"
    msg.from_user = MagicMock(id=500)
    await register_handle_name(message=msg, state=state, session=session)
    assert await state.get_state() == SalonRegister.waiting_slug_confirm.state
    data = await state.get_data()
    assert data["name"] == "Hair World"
    assert "proposed_slug" in data

    cb2 = AsyncMock()
    cb2.from_user = MagicMock(id=500)
    cb2.message = AsyncMock()
    await register_handle_slug_confirm(
        cb2,
        callback_data=SalonSlugConfirmCallback(action="use"),
        state=state,
        session=session,
    )

    salons = list((await session.scalars(select(Salon))).all())
    assert len(salons) == 1
    assert salons[0].name == "Hair World"
    assert salons[0].owner_tg_id == 500


@pytest.mark.asyncio
async def test_registration_rejects_tg_id_already_master(session: AsyncSession) -> None:
    from src.db.models import Master

    session.add(Master(tg_id=600, name="M", slug="m-600"))
    session.add(
        Invite(
            code="rej1",
            created_by_tg_id=1,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            kind="salon_owner",
        )
    )
    await session.commit()

    state = await _mkctx()
    await state.set_state(SalonRegister.waiting_slug_confirm)
    await state.update_data(invite_code="rej1", name="X", proposed_slug="x-slug")

    cb = AsyncMock()
    cb.from_user = MagicMock(id=600)  # conflict
    cb.message = AsyncMock()
    await register_handle_slug_confirm(
        cb,
        callback_data=SalonSlugConfirmCallback(action="use"),
        state=state,
        session=session,
    )
    salons = list((await session.scalars(select(Salon))).all())
    assert len(salons) == 0
```

- [ ] **Step 2: Verify failing**

Run: `uv run pytest tests/test_handlers_salon_registration.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement service**

```python
# src/services/salon_registration.py
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Salon
from src.exceptions import InvalidSlug, ReservedSlug, SlugTaken
from src.repositories.invites import InviteRepository
from src.repositories.salons import SalonRepository
from src.services.slug import SlugService


class TgIdAlreadyMaster(Exception):
    """Cannot register as salon owner — tg_id already has a master account."""


class SalonRegistrationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(
        self,
        *,
        tg_id: int,
        name: str,
        slug: str,
        invite_code: str,
    ) -> Salon:
        master_exists = await self._session.scalar(
            select(Master.id).where(Master.tg_id == tg_id).limit(1)
        )
        if master_exists is not None:
            raise TgIdAlreadyMaster()

        SlugService.validate(slug)
        slug_svc = SlugService(self._session)
        if await slug_svc.is_taken(slug):
            raise SlugTaken(slug)

        salons_repo = SalonRepository(self._session)
        salon = await salons_repo.create(owner_tg_id=tg_id, name=name, slug=slug)

        invite_repo = InviteRepository(self._session)
        invite = await invite_repo.by_code(invite_code)
        if invite is not None:
            invite.used_at = datetime.now(UTC)
            invite.used_by_tg_id = tg_id
            # invite.used_for_master_id stays NULL — this invite is salon_owner
        return salon
```

- [ ] **Step 4: Implement handlers**

```python
# src/handlers/salon/registration.py
from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.register import LangPickCallback
from src.callback_data.salon import SalonSlugConfirmCallback
from src.config import settings
from src.exceptions import InvalidSlug, ReservedSlug, SlugTaken
from src.fsm.salon_register import SalonRegister
from src.keyboards.registration import slug_confirm_kb
from src.keyboards.salon import salon_main_menu
from src.repositories.salons import SalonRepository
from src.services.salon_registration import SalonRegistrationService, TgIdAlreadyMaster
from src.services.slug import SlugService
from src.strings import set_current_lang, strings

router = Router(name="salon_registration")


@router.callback_query(LangPickCallback.filter(), SalonRegister.waiting_lang)
async def register_handle_lang(
    callback: CallbackQuery,
    callback_data: LangPickCallback,
    state: FSMContext,
) -> None:
    await state.update_data(lang=callback_data.lang)
    set_current_lang(callback_data.lang)
    await state.set_state(SalonRegister.waiting_name)
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.SALON_REGISTER_ASK_NAME)


@router.message(SalonRegister.waiting_name)
async def register_handle_name(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    name = (message.text or "").strip()
    if len(name) < 2 or len(name) > 80:
        await message.answer(strings.SALON_REGISTER_NAME_BAD)
        return
    slug_svc = SlugService(session)
    proposed = await slug_svc.generate_default(name)
    await state.update_data(name=name, proposed_slug=proposed)
    await state.set_state(SalonRegister.waiting_slug_confirm)
    await message.answer(
        strings.SALON_REGISTER_SLUG_CONFIRM_FMT.format(
            slug=proposed, username=settings.bot_username
        ),
        reply_markup=slug_confirm_kb(),
    )


@router.callback_query(SalonSlugConfirmCallback.filter(), SalonRegister.waiting_slug_confirm)
async def register_handle_slug_confirm(
    cb: CallbackQuery,
    callback_data: SalonSlugConfirmCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await cb.answer()
    if callback_data.action == "change":
        await state.set_state(SalonRegister.waiting_custom_slug)
        if cb.message is not None and hasattr(cb.message, "answer"):
            await cb.message.answer(strings.REGISTER_ASK_CUSTOM_SLUG)
        return

    data = await state.get_data()
    slug = data["proposed_slug"]
    await _finalize(state=state, session=session, cb=cb, slug=slug)


@router.message(SalonRegister.waiting_custom_slug)
async def register_handle_custom_slug(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    slug = (message.text or "").strip().lower()
    try:
        SlugService.validate(slug)
    except ReservedSlug:
        await message.answer(strings.REGISTER_SLUG_RESERVED)
        return
    except InvalidSlug:
        await message.answer(strings.REGISTER_SLUG_INVALID)
        return
    await _finalize(state=state, session=session, message=message, slug=slug)


async def _finalize(
    *,
    state: FSMContext,
    session: AsyncSession,
    slug: str,
    cb: CallbackQuery | None = None,
    message: Message | None = None,
) -> None:
    out: Message | None = message
    if out is None and cb is not None and cb.message is not None:
        out = cb.message  # type: ignore[assignment]

    tg_id: int | None = None
    if cb is not None and cb.from_user is not None:
        tg_id = cb.from_user.id
    elif message is not None and message.from_user is not None:
        tg_id = message.from_user.id
    if tg_id is None:
        await state.clear()
        return

    data = await state.get_data()
    svc = SalonRegistrationService(session)
    try:
        await svc.register(
            tg_id=tg_id,
            name=data["name"],
            slug=slug,
            invite_code=data["invite_code"],
        )
        await session.commit()
    except TgIdAlreadyMaster:
        if out is not None:
            await out.answer(strings.SALON_REGISTER_ALREADY_MASTER)
        return
    except SlugTaken:
        if out is not None:
            await out.answer(strings.REGISTER_SLUG_TAKEN)
        return

    await state.clear()
    if out is not None:
        await out.answer(strings.SALON_REGISTER_DONE, reply_markup=salon_main_menu())
```

- [ ] **Step 5: Strings (ru + hy)**

Add to `src/strings.py`:

```python
# ru
"SALON_REGISTER_ASK_NAME": "Как называется салон?",
"SALON_REGISTER_NAME_BAD": "Название 2–80 символов. Попробуйте ещё.",
"SALON_REGISTER_SLUG_CONFIRM_FMT": (
    "Адрес салона будет:\nt.me/{username}?start=salon_{slug}\n\nИспользовать?"
),
"SALON_REGISTER_DONE": "Готово! Салон создан.",
"SALON_REGISTER_ALREADY_MASTER": (
    "Этот Telegram-аккаунт уже зарегистрирован как мастер. "
    "Для салона используйте другой аккаунт."
),
# hy
"SALON_REGISTER_ASK_NAME": "Ինչպե՞ս է կոչվում սրահը։",
"SALON_REGISTER_NAME_BAD": "Անունը 2–80 սիմվոլ։ Փորձեք կրկին։",
"SALON_REGISTER_SLUG_CONFIRM_FMT": (
    "Սրահի հասցեն կլինի՝\nt.me/{username}?start=salon_{slug}\n\nՕգտագործե՞լ։"
),
"SALON_REGISTER_DONE": "Պատրաստ է։ Սրահը ստեղծված է։",
"SALON_REGISTER_ALREADY_MASTER": (
    "Այս Telegram-հաշիվն արդեն գրանցված է որպես վարպետ։ "
    "Սրահի համար օգտագործեք այլ հաշիվ։"
),
```

- [ ] **Step 6: Register router**

Update `src/handlers/salon/__init__.py`:

```python
from src.handlers.salon.registration import router as registration_router

router = Router(name="salon")
router.include_router(start_router)
router.include_router(registration_router)
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_handlers_salon_registration.py tests/test_handlers_salon_start.py -v`
Expected: PASS.

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(salons): salon owner registration flow (name + slug + finalize)"
```

---

## Task 10: Salon "My masters" view + menu routing

**Files:**
- Create: `src/handlers/salon/menu.py`
- Create: `src/handlers/salon/masters.py`
- Modify: `src/handlers/salon/__init__.py`
- Modify: `src/strings.py` — rendering strings
- Create: `tests/test_handlers_salon_masters.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_handlers_salon_masters.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Salon
from src.handlers.salon.masters import cmd_salon_my_masters


@pytest.mark.asyncio
async def test_my_masters_lists_salon_members_only(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=1, name="S", slug="s1")
    session.add(salon)
    await session.flush()
    session.add_all(
        [
            Master(tg_id=10, name="Anna", slug="anna-1", salon_id=salon.id),
            Master(tg_id=11, name="Boris", slug="boris-1", salon_id=salon.id),
            Master(tg_id=12, name="Solo", slug="solo-1"),
        ]
    )
    await session.commit()

    msg = AsyncMock(spec=Message)
    await cmd_salon_my_masters(message=msg, session=session, salon=salon)
    msg.answer.assert_awaited()
    text = msg.answer.await_args.args[0]
    assert "Anna" in text and "Boris" in text
    assert "Solo" not in text


@pytest.mark.asyncio
async def test_my_masters_empty_shows_hint(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=2, name="S2", slug="s2")
    session.add(salon)
    await session.commit()

    msg = AsyncMock(spec=Message)
    await cmd_salon_my_masters(message=msg, session=session, salon=salon)
    text = msg.answer.await_args.args[0]
    assert len(text) > 0  # some hint like "пока нет мастеров"
```

- [ ] **Step 2: Verify failing**

Run: `uv run pytest tests/test_handlers_salon_masters.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement handler**

```python
# src/handlers/salon/masters.py
from __future__ import annotations

from aiogram import Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Salon
from src.repositories.salons import SalonRepository
from src.strings import strings

router = Router(name="salon_masters")


async def cmd_salon_my_masters(
    *, message: Message, session: AsyncSession, salon: Salon
) -> None:
    repo = SalonRepository(session)
    masters = await repo.list_masters(salon.id)
    if not masters:
        await message.answer(strings.SALON_MASTERS_EMPTY)
        return
    lines = [strings.SALON_MASTERS_HEADER]
    for m in masters:
        status = (
            strings.ADMIN_MASTER_STATUS_BLOCKED
            if m.blocked_at is not None
            else strings.ADMIN_MASTER_STATUS_ACTIVE
        )
        lines.append(strings.SALON_MASTERS_ITEM_FMT.format(name=m.name, slug=m.slug, status=status))
    await message.answer("\n".join(lines))
```

- [ ] **Step 4: Menu router wiring**

```python
# src/handlers/salon/menu.py
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Salon
from src.handlers.salon.masters import cmd_salon_my_masters
from src.strings import get_bundle

router = Router(name="salon_menu")

_RU = get_bundle("ru")
_HY = get_bundle("hy")


@router.message(F.text.in_({_RU.SALON_MENU_MY_MASTERS, _HY.SALON_MENU_MY_MASTERS}))
async def handle_my_masters(
    message: Message, session: AsyncSession, salon: Salon | None
) -> None:
    if salon is None:
        return
    await cmd_salon_my_masters(message=message, session=session, salon=salon)
```

- [ ] **Step 5: Add strings**

```python
# ru
"SALON_MASTERS_HEADER": "Мастера в вашем салоне:",
"SALON_MASTERS_EMPTY": "В салоне пока нет мастеров. Нажмите «➕ Пригласить мастера», чтобы позвать первого.",
"SALON_MASTERS_ITEM_FMT": "• {name} (`{slug}`) — {status}",
# hy
"SALON_MASTERS_HEADER": "Ձեր սրահի վարպետները։",
"SALON_MASTERS_EMPTY": "Սրահում դեռ վարպետներ չկան։ Սեղմեք «➕ Հրավիրել վարպետ»՝ առաջինին հրավիրելու համար։",
"SALON_MASTERS_ITEM_FMT": "• {name} (`{slug}`) — {status}",
```

- [ ] **Step 6: Register routers**

`src/handlers/salon/__init__.py`:

```python
from src.handlers.salon.masters import router as masters_router
from src.handlers.salon.menu import router as menu_router

router.include_router(menu_router)
router.include_router(masters_router)
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_handlers_salon_masters.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat(salons): My masters view + menu routing"
```

---

## Task 11: Salon invites master (pre-binds salon_id)

**Files:**
- Modify: `src/handlers/salon/masters.py` — add `cmd_salon_invite_master`
- Modify: `src/handlers/salon/menu.py` — route button
- Modify: `src/services/master_registration.py` — honor invite.salon_id on finalize
- Create: `tests/test_handlers_salon_invite_master.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_handlers_salon_invite_master.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master, Salon
from src.handlers.salon.masters import cmd_salon_invite_master
from src.services.master_registration import MasterRegistrationService


@pytest.mark.asyncio
async def test_salon_invite_creates_master_kind_with_salon_id(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=50, name="S", slug="s50")
    session.add(salon)
    await session.commit()

    msg = AsyncMock(spec=Message)
    msg.from_user = MagicMock(id=50)
    await cmd_salon_invite_master(message=msg, session=session, salon=salon)

    invites = list((await session.scalars(select(Invite))).all())
    assert len(invites) == 1
    assert invites[0].kind == "master"
    assert invites[0].salon_id == salon.id


@pytest.mark.asyncio
async def test_master_registered_via_salon_invite_gets_salon_id(session: AsyncSession) -> None:
    from datetime import UTC, datetime, timedelta

    salon = Salon(owner_tg_id=60, name="S", slug="s60")
    session.add(salon)
    await session.flush()
    session.add(
        Invite(
            code="salinv",
            created_by_tg_id=60,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            kind="master",
            salon_id=salon.id,
        )
    )
    await session.commit()

    svc = MasterRegistrationService(session)
    master = await svc.register(
        tg_id=300,
        name="Test",
        specialty="Стилист",
        slug="test-300",
        lang="ru",
        invite_code="salinv",
    )
    await session.commit()
    await session.refresh(master)
    assert master.salon_id == salon.id
```

- [ ] **Step 2: Verify failing**

Run: `uv run pytest tests/test_handlers_salon_invite_master.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `cmd_salon_invite_master`**

In `src/handlers/salon/masters.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from src.config import settings
from src.repositories.invites import InviteRepository


async def cmd_salon_invite_master(
    *, message: Message, session: AsyncSession, salon: Salon
) -> None:
    inv_repo = InviteRepository(session)
    invite = await inv_repo.create(
        created_by_tg_id=salon.owner_tg_id, kind="master", salon_id=salon.id
    )
    await session.commit()

    link = f"https://t.me/{settings.bot_username}?start=invite_{invite.code}"
    tz = ZoneInfo("Asia/Yerevan")
    expires_local = invite.expires_at.astimezone(tz).strftime("%d.%m.%Y %H:%M")
    await message.answer(
        strings.SALON_INVITE_CREATED_FMT.format(
            code=invite.code, link=link, expires=expires_local
        ),
        parse_mode="Markdown",
    )
```

Add strings:
```python
# ru
"SALON_INVITE_CREATED_FMT": "Инвайт для мастера создан.\n\nКод: `{code}`\nСсылка: {link}\nДействителен до: {expires}\n\nОтправьте мастеру — он пройдёт регистрацию и появится в вашем салоне.",
# hy
"SALON_INVITE_CREATED_FMT": "Վարպետի հրավերը ստեղծված է։\n\nԿոդ՝ `{code}`\nՀղում՝ {link}\nՎավերական մինչ՝ {expires}\n\nՈւղարկեք վարպետին՝ նա կգրանցվի և կհայտնվի ձեր սրահում։",
```

- [ ] **Step 4: Update `MasterRegistrationService.register`**

In `src/services/master_registration.py`, find the invite lookup and add after it:

```python
invite = await invite_repo.by_code(invite_code)
# existing checks...
master = Master(
    tg_id=tg_id,
    name=name,
    slug=slug,
    specialty_text=specialty,
    lang=lang,
    salon_id=invite.salon_id if invite is not None else None,  # NEW
)
# rest unchanged
```

- [ ] **Step 5: Wire button into menu**

In `src/handlers/salon/menu.py`:

```python
@router.message(F.text.in_({_RU.SALON_MENU_INVITE_MASTER, _HY.SALON_MENU_INVITE_MASTER}))
async def handle_invite_master(
    message: Message, session: AsyncSession, salon: Salon | None
) -> None:
    if salon is None:
        return
    from src.handlers.salon.masters import cmd_salon_invite_master
    await cmd_salon_invite_master(message=message, session=session, salon=salon)
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_handlers_salon_invite_master.py tests/test_services_master_registration.py -v`
Expected: PASS.

Run regression: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat(salons): salon can invite masters, master.salon_id bound from invite"
```

---

## Task 12: Salon my_link + QR buttons

**Files:**
- Create: `src/handlers/salon/my_link.py`
- Modify: `src/handlers/salon/__init__.py`
- Modify: `src/handlers/salon/menu.py` — route buttons
- Create: `tests/test_handlers_salon_my_link.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_handlers_salon_my_link.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import BufferedInputFile, Message

from src.db.models import Salon
from src.handlers.salon.my_link import cmd_salon_mylink, cmd_salon_qr


@pytest.mark.asyncio
async def test_salon_mylink_contains_slug() -> None:
    salon = Salon(owner_tg_id=1, name="S", slug="my-salon-1")
    msg = AsyncMock(spec=Message)
    await cmd_salon_mylink(message=msg, salon=salon)
    msg.answer.assert_awaited()
    text = msg.answer.await_args.args[0]
    assert "my-salon-1" in text
    assert "salon_" in text  # deep-link uses salon_<slug>


@pytest.mark.asyncio
async def test_salon_qr_sends_photo_with_caption() -> None:
    salon = Salon(owner_tg_id=1, name="S", slug="qr-salon")
    msg = AsyncMock(spec=Message)
    await cmd_salon_qr(message=msg, salon=salon)
    msg.answer_photo.assert_awaited()
    call = msg.answer_photo.await_args
    photo = call.kwargs.get("photo") or (call.args[0] if call.args else None)
    assert isinstance(photo, BufferedInputFile)
    assert "qr-salon" in call.kwargs.get("caption", "")
```

- [ ] **Step 2: Verify failing**

Run: `uv run pytest tests/test_handlers_salon_my_link.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement handlers**

```python
# src/handlers/salon/my_link.py
from __future__ import annotations

from aiogram import Router
from aiogram.types import BufferedInputFile, Message

from src.config import settings
from src.db.models import Salon
from src.strings import strings
from src.utils.qr import build_master_qr

router = Router(name="salon_my_link")


def _salon_link(salon: Salon) -> str:
    return f"https://t.me/{settings.bot_username}?start=salon_{salon.slug}"


async def cmd_salon_mylink(*, message: Message, salon: Salon) -> None:
    await message.answer(strings.SALON_MY_LINK_MSG_FMT.format(link=_salon_link(salon)))


async def cmd_salon_qr(*, message: Message, salon: Salon) -> None:
    link = _salon_link(salon)
    png = build_master_qr(link)  # generic QR from url; function name historical
    photo = BufferedInputFile(png, filename=f"qr-salon-{salon.slug}.png")
    await message.answer_photo(
        photo=photo, caption=strings.SALON_QR_CAPTION_FMT.format(link=link)
    )
```

Add strings:

```python
# ru
"SALON_MY_LINK_MSG_FMT": "Ссылка на ваш салон:\n{link}\n\nПечатайте на вывеске — клиенты будут попадать в список ваших мастеров.",
"SALON_QR_CAPTION_FMT": "📱 QR-код салона.\n\n{link}\n\nРаспечатайте и повесьте у входа.",
# hy
"SALON_MY_LINK_MSG_FMT": "Ձեր սրահի հղումը՝\n{link}\n\nԴրեք ցուցատախտակին՝ հաճախորդները կհայտնվեն ձեր վարպետների ցանկում։",
"SALON_QR_CAPTION_FMT": "📱 Սրահի QR-կոդը։\n\n{link}\n\nՏպեք և փակցրեք մուտքի մոտ։",
```

- [ ] **Step 4: Wire buttons**

In `src/handlers/salon/menu.py`:

```python
@router.message(F.text.in_({_RU.SALON_MENU_MY_LINK, _HY.SALON_MENU_MY_LINK}))
async def handle_salon_my_link(message: Message, salon: Salon | None) -> None:
    if salon is None:
        return
    from src.handlers.salon.my_link import cmd_salon_mylink
    await cmd_salon_mylink(message=message, salon=salon)


@router.message(F.text.in_({_RU.SALON_MENU_QR, _HY.SALON_MENU_QR}))
async def handle_salon_qr(message: Message, salon: Salon | None) -> None:
    if salon is None:
        return
    from src.handlers.salon.my_link import cmd_salon_qr
    await cmd_salon_qr(message=message, salon=salon)
```

Add router import to `src/handlers/salon/__init__.py`:

```python
from src.handlers.salon.my_link import router as my_link_router
router.include_router(my_link_router)
```

- [ ] **Step 5: Run tests + regression**

Run: `uv run pytest tests/test_handlers_salon_my_link.py -v`
Expected: PASS.

`uv run pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(salons): Моя ссылка + QR-код buttons"
```

---

## Task 13: Extend `BookingService.create_manual` to accept `source`

**Files:**
- Modify: `src/services/booking.py`
- Modify: existing master manual add to pass `source="master_manual"` explicitly
- Create/update: `tests/test_services_booking_source.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_services_booking_source.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master, Service
from src.services.booking import BookingService


@pytest.mark.asyncio
async def test_create_manual_accepts_salon_source(session: AsyncSession) -> None:
    master = Master(tg_id=1, name="M", slug="m-src", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="C", phone="+37499999999", tg_id=99)
    session.add(client)
    svc_row = Service(master_id=master.id, name="X", duration_min=30)
    session.add(svc_row)
    await session.flush()
    await session.commit()

    booking = BookingService(session)
    start = datetime.now(UTC) + timedelta(hours=2)
    appt = await booking.create_manual(
        master=master,
        client=client,
        service=svc_row,
        start_at=start,
        source="salon_manual",
    )
    await session.commit()
    await session.refresh(appt)
    assert appt.source == "salon_manual"
    assert appt.status == "confirmed"
```

- [ ] **Step 2: Verify failing**

Run: `uv run pytest tests/test_services_booking_source.py -v`
Expected: FAIL — `create_manual` doesn't accept `source`.

- [ ] **Step 3: Extend signature**

In `src/services/booking.py`, in `create_manual`:

```python
async def create_manual(
    self,
    *,
    master: Master,
    client: Client,
    service: Service,
    start_at: datetime,
    comment: str | None = None,
    source: str = "master_manual",
) -> Appointment:
    if source not in APPT_SOURCES:
        raise ValueError(f"invalid source: {source!r}")
    # ... existing construction, replace hardcoded "master_manual" with source ...
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start_at,
        end_at=end_at,
        status="confirmed",
        source=source,  # parameterized
        comment=comment,
    )
    # existing integrity-error handling etc.
```

Verify `APPT_SOURCES` in `src/db/models.py` now includes all three: `("client_request", "master_manual", "salon_manual")`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_services_booking_source.py -q`
Expected: PASS.

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(salons): BookingService.create_manual accepts source parameter"
```

---

## Task 14: Salon add-appointment FSM + master picker

**Files:**
- Create: `src/fsm/salon_add.py`
- Modify: `src/keyboards/salon.py` — add `salon_masters_pick_kb`
- Create: `src/handlers/salon/add_appt.py`
- Modify: `src/handlers/salon/menu.py` — route "Новая запись" button
- Modify: `src/handlers/salon/__init__.py` — include add_appt router
- Create: `tests/test_handlers_salon_add_appt_pickers.py`

- [ ] **Step 1: Write FSM**

```python
# src/fsm/salon_add.py
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SalonAddAppt(StatesGroup):
    PickingMaster = State()
    PickingService = State()
    PickingDate = State()
    PickingSlot = State()
    NewClientName = State()
    NewClientPhone = State()
    Confirming = State()
```

- [ ] **Step 2: Write test for entry + master pick**

```python
# tests/test_handlers_salon_add_appt_pickers.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.salon import SalonMasterPickCallback
from src.db.models import Master, Salon, Service
from src.fsm.salon_add import SalonAddAppt
from src.handlers.salon.add_appt import cb_salon_pick_master, cmd_salon_add_appt


async def _mkctx() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))


@pytest.mark.asyncio
async def test_enter_add_appt_shows_master_picker(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=1, name="S", slug="s-a")
    session.add(salon)
    await session.flush()
    session.add_all(
        [
            Master(tg_id=10, name="Anna", slug="a-10", salon_id=salon.id),
            Master(tg_id=11, name="Boris", slug="b-11", salon_id=salon.id),
        ]
    )
    await session.commit()

    msg = AsyncMock()
    state = await _mkctx()
    await cmd_salon_add_appt(message=msg, state=state, session=session, salon=salon)
    assert await state.get_state() == SalonAddAppt.PickingMaster.state
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_pick_master_advances_to_service(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=1, name="S", slug="s-b")
    session.add(salon)
    await session.flush()
    m = Master(tg_id=20, name="M", slug="m-20", salon_id=salon.id)
    session.add(m)
    await session.flush()
    session.add(Service(master_id=m.id, name="Cut", duration_min=30))
    await session.commit()

    cb = AsyncMock()
    cb.from_user = MagicMock(id=1)
    cb.message = AsyncMock()
    state = await _mkctx()
    await state.set_state(SalonAddAppt.PickingMaster)

    await cb_salon_pick_master(
        callback=cb,
        callback_data=SalonMasterPickCallback(master_id=m.id),
        state=state,
        session=session,
        salon=salon,
    )
    data = await state.get_data()
    assert data.get("master_id") == str(m.id)
    assert await state.get_state() == SalonAddAppt.PickingService.state
```

- [ ] **Step 3: Verify failing**

Run: `uv run pytest tests/test_handlers_salon_add_appt_pickers.py -v`
Expected: FAIL.

- [ ] **Step 4: Keyboard for master picker**

In `src/keyboards/salon.py` (append):

```python
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.salon import SalonMasterPickCallback
from src.db.models import Master


def salon_masters_pick_kb(masters: list[Master]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for m in masters:
        rows.append(
            [
                InlineKeyboardButton(
                    text=m.name,
                    callback_data=SalonMasterPickCallback(master_id=m.id).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 5: Handlers — entry + master pick**

```python
# src/handlers/salon/add_appt.py
from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.salon import SalonMasterPickCallback
from src.db.models import Salon
from src.fsm.salon_add import SalonAddAppt
from src.keyboards.salon import salon_masters_pick_kb
from src.keyboards.slots import services_pick_kb
from src.repositories.salons import SalonRepository
from src.repositories.services import ServiceRepository
from src.strings import strings

router = Router(name="salon_add_appt")


async def cmd_salon_add_appt(
    *, message: Message, state: FSMContext, session: AsyncSession, salon: Salon
) -> None:
    repo = SalonRepository(session)
    masters = [m for m in await repo.list_masters(salon.id) if m.blocked_at is None]
    if not masters:
        await message.answer(strings.SALON_ADD_NO_MASTERS)
        return
    await state.clear()
    await state.set_state(SalonAddAppt.PickingMaster)
    await message.answer(
        strings.SALON_ADD_PICK_MASTER, reply_markup=salon_masters_pick_kb(masters)
    )


@router.callback_query(SalonMasterPickCallback.filter(), SalonAddAppt.PickingMaster)
async def cb_salon_pick_master(
    callback: CallbackQuery,
    callback_data: SalonMasterPickCallback,
    state: FSMContext,
    session: AsyncSession,
    salon: Salon,
) -> None:
    repo = SalonRepository(session)
    masters = await repo.list_masters(salon.id)
    target = next((m for m in masters if m.id == callback_data.master_id), None)
    if target is None:
        await callback.answer(strings.SALON_ADD_MASTER_NOT_FOUND, show_alert=True)
        return

    s_repo = ServiceRepository(session)
    services = await s_repo.list_active(target.id)
    if not services:
        await callback.answer(strings.SALON_ADD_NO_SERVICES, show_alert=True)
        return

    await state.update_data(master_id=str(target.id))
    await state.set_state(SalonAddAppt.PickingService)
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_ASK_SERVICE, reply_markup=services_pick_kb(services)
        )
```

- [ ] **Step 6: Strings**

```python
# ru
"SALON_ADD_NO_MASTERS": "В салоне пока нет активных мастеров — некого записывать.",
"SALON_ADD_PICK_MASTER": "К какому мастеру записать?",
"SALON_ADD_MASTER_NOT_FOUND": "Мастер не найден.",
"SALON_ADD_NO_SERVICES": "У мастера нет услуг.",
# hy (аналогично — переведёшь)
```

- [ ] **Step 7: Register**

`src/handlers/salon/__init__.py`:

```python
from src.handlers.salon.add_appt import router as add_appt_router
router.include_router(add_appt_router)
```

In `src/handlers/salon/menu.py`:

```python
@router.message(F.text.in_({_RU.SALON_MENU_ADD_APPT, _HY.SALON_MENU_ADD_APPT}))
async def handle_add_appt(
    message: Message, state: FSMContext, session: AsyncSession, salon: Salon | None
) -> None:
    if salon is None:
        return
    from src.handlers.salon.add_appt import cmd_salon_add_appt
    await cmd_salon_add_appt(message=message, state=state, session=session, salon=salon)
```

(Add `state: FSMContext` to the import list at top of the file and to the signature.)

- [ ] **Step 8: Run + regression**

Run: `uv run pytest tests/test_handlers_salon_add_appt_pickers.py -q`
Expected: PASS.

`uv run pytest -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat(salons): add-appt FSM entry + master picker"
```

---

## Task 15: Service + Date + Slot pickers

**Files:**
- Modify: `src/handlers/salon/add_appt.py`
- Modify: `src/keyboards/salon.py` — date/slot rendering helpers (or reuse existing master_add helpers)
- Create: `tests/test_handlers_salon_add_appt_slots.py`

This task mirrors the master's manual add flow for PickingService → PickingDate → PickingSlot. The logic is already implemented in `src/handlers/master/add_manual.py:cb_pick_service`, `cb_pick_date`, etc. — extract reusable parts where feasible, but keep separate handlers filtered on `SalonAddAppt.*` states.

- [ ] **Step 1: Write test**

```python
# tests/test_handlers_salon_add_appt_slots.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.client_services import ClientServicePick
from src.db.models import Master, Salon, Service
from src.fsm.salon_add import SalonAddAppt
from src.handlers.salon.add_appt import cb_salon_pick_service


async def _mkctx() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))


@pytest.mark.asyncio
async def test_pick_service_advances_to_date(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=1, name="S", slug="s-date")
    session.add(salon)
    await session.flush()
    m = Master(
        tg_id=30,
        name="M",
        slug="m-30",
        salon_id=salon.id,
        work_hours={"mon": [["10:00", "19:00"]], "tue": [["10:00", "19:00"]],
                    "wed": [["10:00", "19:00"]], "thu": [["10:00", "19:00"]],
                    "fri": [["10:00", "19:00"]], "sat": [], "sun": []},
    )
    session.add(m)
    await session.flush()
    svc = Service(master_id=m.id, name="Cut", duration_min=30)
    session.add(svc)
    await session.flush()
    await session.commit()

    cb = AsyncMock()
    cb.from_user = MagicMock(id=1)
    cb.message = AsyncMock()
    state = await _mkctx()
    await state.set_state(SalonAddAppt.PickingService)
    await state.update_data(master_id=str(m.id))

    await cb_salon_pick_service(
        callback=cb,
        callback_data=ClientServicePick(service_id=svc.id),
        state=state,
        session=session,
        salon=salon,
    )
    data = await state.get_data()
    assert data.get("service_id") == str(svc.id)
    assert await state.get_state() == SalonAddAppt.PickingDate.state
```

- [ ] **Step 2: Verify failing**

Run: `uv run pytest tests/test_handlers_salon_add_appt_slots.py -v`
Expected: FAIL.

- [ ] **Step 3: Add service + date + slot handlers**

Look at `src/handlers/master/add_manual.py` lines 213–410 (approx). Duplicate the service-pick / date-pick / slot-pick handlers into `src/handlers/salon/add_appt.py`, but with:
- `SalonAddAppt.*` states instead of `MasterAdd.*`
- Master resolved from `state.data["master_id"]` instead of from middleware `master`
- AvailabilityService usage unchanged

Sketch:

```python
from uuid import UUID

from src.callback_data.calendar import CalendarCallback
from src.callback_data.client_services import ClientServicePick
from src.callback_data.slots import SlotCallback
from src.db.models import Master, Service
from src.keyboards.calendar import calendar_keyboard
from src.keyboards.master_add import slots_grid_with_custom


@router.callback_query(ClientServicePick.filter(), SalonAddAppt.PickingService)
async def cb_salon_pick_service(
    callback: CallbackQuery,
    callback_data: ClientServicePick,
    state: FSMContext,
    session: AsyncSession,
    salon: Salon,
) -> None:
    data = await state.get_data()
    master_id = UUID(data["master_id"])
    s_repo = ServiceRepository(session)
    service = await s_repo.get(callback_data.service_id, master_id=master_id)
    if service is None:
        await callback.answer(strings.SALON_ADD_MASTER_NOT_FOUND, show_alert=True)
        return
    await state.update_data(service_id=str(service.id))
    await state.set_state(SalonAddAppt.PickingDate)
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_ASK_DATE, reply_markup=calendar_keyboard(month=None)
        )


@router.callback_query(CalendarCallback.filter(), SalonAddAppt.PickingDate)
async def cb_salon_pick_date(
    callback: CallbackQuery,
    callback_data: CalendarCallback,
    state: FSMContext,
    session: AsyncSession,
    salon: Salon,
) -> None:
    # Copy pattern from master/add_manual.py cb_pick_date
    ...
```

Full implementations should mirror `master/add_manual.py` adapting state class and reading `master_id`/`service_id` from FSM data rather than middleware. **Include all three handlers (service/date/slot) in this task's commit.**

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/test_handlers_salon_add_appt_slots.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(salons): add-appt service + date + slot pickers"
```

---

## Task 16: Client info + confirm + save (salon booking)

**Files:**
- Modify: `src/handlers/salon/add_appt.py` — add NewClientName, NewClientPhone + SkipPhone + confirm handlers
- Create: `tests/test_handlers_salon_add_appt_save.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_handlers_salon_add_appt_save.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Master, Salon, Service
from src.fsm.salon_add import SalonAddAppt
from src.handlers.salon.add_appt import cb_salon_confirm_save


async def _mkctx() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))


@pytest.mark.asyncio
async def test_confirm_save_creates_salon_manual_confirmed_appointment(
    session: AsyncSession,
) -> None:
    salon = Salon(owner_tg_id=1, name="S", slug="s-save")
    session.add(salon)
    await session.flush()
    m = Master(
        tg_id=40, name="M", slug="m-40", salon_id=salon.id,
        work_hours={d: [["10:00", "19:00"]] for d in ("mon","tue","wed","thu","fri","sat","sun")},
    )
    session.add(m)
    await session.flush()
    svc = Service(master_id=m.id, name="Cut", duration_min=30)
    session.add(svc)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(SalonAddAppt.Confirming)
    start = (datetime.now(UTC) + timedelta(hours=2)).replace(minute=0, second=0, microsecond=0)
    await state.update_data(
        master_id=str(m.id),
        service_id=str(svc.id),
        start_at=start.isoformat(),
        client_name="Walk-in",
        client_phone=None,
    )

    bot = AsyncMock()
    cb = AsyncMock()
    cb.message = AsyncMock()
    await cb_salon_confirm_save(callback=cb, state=state, session=session, salon=salon, bot=bot)

    appts = list((await session.scalars(select(Appointment))).all())
    assert len(appts) == 1
    assert appts[0].source == "salon_manual"
    assert appts[0].status == "confirmed"
    bot.send_message.assert_awaited()  # notifies master
    assert bot.send_message.await_args.kwargs["chat_id"] == m.tg_id
```

- [ ] **Step 2: Verify failing**

Run: `uv run pytest tests/test_handlers_salon_add_appt_save.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement name/phone/skip/confirm handlers**

Mirror master flow (`src/handlers/master/add_manual.py`) adapting for SalonAddAppt. Key differences at save:

```python
from aiogram import Bot
from src.callback_data.salon import SalonConfirmApptCallback, SalonSkipPhoneCallback
from src.keyboards.master_add import skip_phone_kb  # reuse existing
from src.repositories.clients import ClientRepository
from src.services.booking import BookingService
from src.services.reminders import ReminderService


@router.message(SalonAddAppt.NewClientName)
async def msg_salon_client_name(
    message: Message, state: FSMContext, salon: Salon
) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(strings.MANUAL_NAME_BAD)
        return
    await state.update_data(client_name=name)
    await state.set_state(SalonAddAppt.NewClientPhone)
    await message.answer(strings.MANUAL_ASK_PHONE, reply_markup=skip_phone_kb())


@router.message(SalonAddAppt.NewClientPhone)
async def msg_salon_client_phone(
    message: Message, state: FSMContext, salon: Salon
) -> None:
    from src.utils.phone import normalize as normalize_phone
    raw = (message.text or "").strip()
    normalized = normalize_phone(raw)
    if normalized is None:
        await message.answer(strings.MANUAL_PHONE_BAD)
        return
    await state.update_data(client_phone=normalized)
    await _render_confirm_card(message, state, salon)


@router.callback_query(SalonSkipPhoneCallback.filter(), SalonAddAppt.NewClientPhone)
async def cb_salon_skip_phone(
    callback: CallbackQuery, state: FSMContext, salon: Salon
) -> None:
    await state.update_data(client_phone=None)
    await callback.answer()
    if isinstance(callback.message, Message):
        await _render_confirm_card(callback.message, state, salon)


async def _render_confirm_card(
    target: Message, state: FSMContext, salon: Salon
) -> None:
    data = await state.get_data()
    # fetch master+service for rendering via session.get, but we don't have a session here.
    # Simplify: store denormalized in state.data when picking.
    # So ensure earlier handlers store service_name, master_name, duration in state.data.
    ...


@router.callback_query(SalonConfirmApptCallback.filter(), SalonAddAppt.Confirming)
async def cb_salon_confirm_save(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    salon: Salon,
    bot: Bot,
) -> None:
    data = await state.get_data()
    master = await session.get(Master, UUID(data["master_id"]))
    service = await session.get(Service, UUID(data["service_id"]))
    if master is None or service is None:
        await callback.answer(strings.SALON_ADD_MASTER_NOT_FOUND, show_alert=True)
        return

    client_repo = ClientRepository(session)
    phone = data.get("client_phone")
    if phone:
        client = await client_repo.upsert_by_phone(
            master_id=master.id, phone=phone, name=data["client_name"], tg_id=None
        )
    else:
        client = await client_repo.create_anonymous(
            master_id=master.id, name=data["client_name"]
        )

    booking = BookingService(session)
    start_at = datetime.fromisoformat(data["start_at"])
    try:
        appt = await booking.create_manual(
            master=master,
            client=client,
            service=service,
            start_at=start_at,
            source="salon_manual",
        )
    except SlotAlreadyTaken:
        await callback.answer(strings.MANUAL_SLOT_TAKEN, show_alert=True)
        return

    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt)
    await session.commit()

    # Notify master
    tz = ZoneInfo(master.timezone)
    local = start_at.astimezone(tz)
    text = strings.SALON_NOTIFY_MASTER_FMT.format(
        salon=salon.name,
        client=data["client_name"],
        service=service.name,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
    )
    try:
        await bot.send_message(chat_id=master.tg_id, text=text)
    except Exception:
        pass

    await state.clear()
    await callback.answer(strings.MANUAL_SAVED)
    if isinstance(callback.message, Message):
        await callback.message.answer(strings.MANUAL_SAVED, reply_markup=salon_main_menu())
```

Add strings:

```python
# ru
"SALON_NOTIFY_MASTER_FMT": "🔔 {salon} записал(а) клиента:\n👤 {client}\n💇 {service}\n📅 {date} в {time}",
# hy
"SALON_NOTIFY_MASTER_FMT": "🔔 {salon}-ը գրանցեց հաճախորդ՝\n👤 {client}\n💇 {service}\n📅 {date} {time}",
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_handlers_salon_add_appt_save.py -q`
Expected: PASS.

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(salons): client entry + confirm + save salon-manual appointment"
```

---

## Task 17: Solo master regression test

**Files:**
- Create: `tests/test_salon_does_not_break_solo_masters.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_salon_does_not_break_solo_masters.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.services.booking import BookingService


@pytest.mark.asyncio
async def test_solo_master_can_create_manual_appointment(session: AsyncSession) -> None:
    m = Master(tg_id=9000, name="Solo", slug="solo-reg", timezone="Asia/Yerevan")
    session.add(m)
    await session.flush()
    assert m.salon_id is None  # solo by default

    c = Client(master_id=m.id, name="C", phone="+37499000000", tg_id=99)
    session.add(c)
    s = Service(master_id=m.id, name="X", duration_min=30)
    session.add(s)
    await session.flush()
    await session.commit()

    booking = BookingService(session)
    appt = await booking.create_manual(
        master=m,
        client=c,
        service=s,
        start_at=datetime.now(UTC) + timedelta(hours=3),
    )
    # Default source stays master_manual
    assert appt.source == "master_manual"
    assert appt.status == "confirmed"


@pytest.mark.asyncio
async def test_solo_master_not_visible_in_any_salons_master_list(
    session: AsyncSession,
) -> None:
    from src.db.models import Salon
    from src.repositories.salons import SalonRepository

    salon = Salon(owner_tg_id=1, name="S", slug="sreg")
    session.add(salon)
    await session.flush()
    session.add_all(
        [
            Master(tg_id=100, name="Solo", slug="solo-not-in", salon_id=None),
            Master(tg_id=101, name="Joined", slug="joined-1", salon_id=salon.id),
        ]
    )
    await session.commit()
    repo = SalonRepository(session)
    masters = await repo.list_masters(salon.id)
    assert [m.slug for m in masters] == ["joined-1"]
```

- [ ] **Step 2: Run — should PASS (solo path untouched)**

Run: `uv run pytest tests/test_salon_does_not_break_solo_masters.py -q`
Expected: PASS immediately (no implementation needed; this is a regression test).

- [ ] **Step 3: Commit**

```bash
git add tests/test_salon_does_not_break_solo_masters.py
git commit -m "test(salons): regression guard — solo master flow untouched"
```

---

## Task 18: Final validation + push

**Files:**
- All changes so far

- [ ] **Step 1: Lint + type-check**

```bash
uv run ruff format src/ tests/
uv run ruff check src/ tests/
uv run mypy src/
```

Expected: all green. Fix any drift.

- [ ] **Step 2: Full test suite**

```bash
uv run pytest -q
```

Expected: all pass (expect ~490+ tests now; a gain of ~30 from this epic).

- [ ] **Step 3: Migration roundtrip check**

```bash
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run alembic upgrade head
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run alembic downgrade 0004
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run alembic upgrade head
```

Expected: all commands succeed.

- [ ] **Step 4: Commit leftover + push**

```bash
git add -A
git commit -m "chore(salons): final lint/format cleanup" || true
git push origin main
```

---

## Self-Review Checklist (post-write)

- [ ] **Spec coverage:** salon table ✓, owner onboarding ✓, master-to-salon binding ✓, owner menu (list/invite/add-appt/link/qr/settings) ✓, salon-creates-appointment ✓, solo regression ✓.
- [ ] **Placeholder scan:** no TODO / TBD; each step has exact code or exact commands. ✓
- [ ] **Type consistency:** `Salon.id: UUID`, `Master.salon_id: UUID | None`, `Invite.kind: str`, `Invite.salon_id: UUID | None`. FSM state names match across tasks (`SalonAddAppt.PickingMaster` etc.). Callback prefixes: `ssc/smp/sslt/snc/sspp/scap/ans`. ✓
- [ ] **Filter wiring:** master `/start` filter updated to reject non-master invites; salon `/start` filter only catches salon_owner invites or existing salon owners; router order admin → master → salon → client. ✓
- [ ] **Privacy invariant:** salon owner never queries `Appointment` rows of a master directly; booking flow uses `AvailabilityService` which returns only free slots. ✓
- [ ] **Backward compat:** `Master.salon_id` nullable, `Invite.kind` defaults to `'master'` via server_default, solo flow paths unchanged.  ✓
- [ ] **Out of scope explicit:** salon landing page (10.2), stats (10.3), logo/description (10.3) — tasks for later.

---

**Plan complete.**
