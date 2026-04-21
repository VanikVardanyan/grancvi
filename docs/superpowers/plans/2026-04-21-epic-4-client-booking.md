# Epic 4 — Client booking FSM + calendar + master approval — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete client-side booking flow (`/start` → service → date → time → name → phone → confirm), notify the master, and handle their confirm/reject/history decisions.

**Architecture:** Slice by layer (pure fns → repos → services → callbacks/fsm → keyboards → handlers) so each task is independently testable. Reuse the existing `BookingService.get_free_slots` / `create_pending` / `confirm` / `reject` from Epic 3. Add `calculate_day_loads` as a new pure function next to `calculate_free_slots`.

**Tech Stack:** Python 3.12, aiogram 3.x, SQLAlchemy 2.0 async, PostgreSQL 16, Redis 7, pytest + pytest-asyncio, ruff + mypy strict.

**Spec:** `docs/superpowers/specs/2026-04-21-epic-4-client-booking-design.md`

**Invariant:** v0.1 has exactly one `Master` row. `/start` without deep-link parameters resolves to that single master via `MasterRepository.get_singleton()`.

**Coverage targets:** `availability.py` 100%, `booking.py` ≥95%, new repositories ≥90%, new utils 100%, handlers ≥60%.

---

## File structure

### Create
- `src/utils/phone.py` — `normalize(raw: str) -> str`, `InvalidPhone` exception-free (returns None on bad input).
- `src/repositories/clients.py` — `ClientRepository` (`get`, `upsert_by_phone`).
- `src/callback_data/calendar.py` — `CalendarCallback`.
- `src/callback_data/slots.py` — `SlotCallback`.
- `src/callback_data/approval.py` — `ApprovalCallback`.
- `src/callback_data/client_services.py` — `ClientServicePick` (distinct prefix from master's `ServiceAction`).
- `src/fsm/client_booking.py` — `ClientBooking` StatesGroup.
- `src/keyboards/calendar.py` — `calendar_keyboard`, `DayLoad` Literal, `MONTH_NAMES_RU`.
- `src/keyboards/slots.py` — `slots_grid`, `confirm_kb`, `services_pick_kb`, `approval_kb`.
- `src/handlers/client/__init__.py` — aggregate router.
- `src/handlers/client/start.py` — `/start`, `/cancel`.
- `src/handlers/client/booking.py` — full FSM.
- `src/handlers/master/approve.py` — `ApprovalCallback` handlers.
- `tests/test_utils_phone.py`
- `tests/test_repositories_clients.py`
- `tests/test_repositories_masters_singleton.py`
- `tests/test_repositories_appointments_epic4.py`
- `tests/test_availability_day_loads.py`
- `tests/test_services_booking_epic4.py`
- `tests/test_callback_data_epic4.py`
- `tests/test_keyboards_calendar.py`
- `tests/test_keyboards_slots.py`
- `tests/test_handlers_client_booking.py`
- `tests/test_handlers_master_approve.py`

### Modify
- `src/repositories/masters.py` — add `get_singleton`.
- `src/repositories/appointments.py` — add `list_active_for_month`, `list_for_client`.
- `src/services/booking.py` — add `get_month_load`, `list_client_history`.
- `src/services/availability.py` — add `calculate_day_loads`, `DayLoad`.
- `src/strings.py` — add client-booking + approval keys to `_RU` and `_HY`.
- `src/handlers/__init__.py` — include client router.
- `src/handlers/master/__init__.py` — include approve router.
- `src/handlers/master/start.py` — remove `START_UNKNOWN` / `CLIENT_STUB` dead branches (client flow now lives in the client router).

---

## Task 1: `utils/phone.py` — normalize Armenian phone

**Files:**
- Create: `src/utils/phone.py`
- Test: `tests/test_utils_phone.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_utils_phone.py`:

```python
from __future__ import annotations

import pytest

from src.utils.phone import normalize


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+374 99 12 34 56", "+37499123456"),
        ("+37499123456", "+37499123456"),
        ("+374-99-12-34-56", "+37499123456"),
        ("+374 (99) 12 34 56", "+37499123456"),
        ("099 12 34 56", "+37499123456"),
        ("099-123-456", "+37499123456"),
        (" +374  99 123 456 ", "+37499123456"),
    ],
)
def test_normalize_valid(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "abc",
        "+1 212 555 1212",  # not +374
        "+37499",  # too short
        "+374991234567",  # too long
        "99123456",  # missing leading 0 and country code
        "++37499123456",  # malformed
    ],
)
def test_normalize_rejects(raw: str) -> None:
    assert normalize(raw) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_utils_phone.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'src.utils.phone').

- [ ] **Step 3: Implement `src/utils/phone.py`**

```python
from __future__ import annotations

import re

_ALLOWED = re.compile(r"[^\d+]")


def normalize(raw: str) -> str | None:
    """Normalize an Armenian phone to E.164 (+374XXXXXXXX).

    Returns None if `raw` cannot be parsed as an Armenian mobile number.
    Accepts `+374 XX XXX XXX`, `+374XXXXXXXX`, `0XX XXX XXX` variants with
    spaces, dashes, or parentheses. Rejects foreign country codes and wrong
    lengths.
    """
    if not raw:
        return None
    cleaned = _ALLOWED.sub("", raw.strip())
    if not cleaned:
        return None
    if cleaned.startswith("+"):
        digits = cleaned[1:]
        if not digits.isdigit():
            return None
        if not digits.startswith("374"):
            return None
        national = digits[3:]
    else:
        if not cleaned.isdigit():
            return None
        if cleaned.startswith("0"):
            national = cleaned[1:]
        elif cleaned.startswith("374"):
            national = cleaned[3:]
        else:
            return None
    if len(national) != 8:
        return None
    return f"+374{national}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_utils_phone.py -v`
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add src/utils/phone.py tests/test_utils_phone.py
git commit -m "feat(utils): phone normalize for +374 with parametrized coverage"
```

---

## Task 2: `MasterRepository.get_singleton`

**Files:**
- Modify: `src/repositories/masters.py`
- Test: `tests/test_repositories_masters_singleton.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_repositories_masters_singleton.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.masters import MasterRepository


@pytest.mark.asyncio
async def test_get_singleton_empty(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    assert await repo.get_singleton() is None


@pytest.mark.asyncio
async def test_get_singleton_returns_only_master(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    created = await repo.create(tg_id=777, name="Единственный")
    await session.commit()

    fetched = await repo.get_singleton()
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_singleton_returns_first_when_multiple(session: AsyncSession) -> None:
    """v0.1 invariant is one master, but be deterministic if it's ever violated."""
    repo = MasterRepository(session)
    a = await repo.create(tg_id=1001, name="Первый")
    await session.commit()
    _ = await repo.create(tg_id=1002, name="Второй")
    await session.commit()

    fetched = await repo.get_singleton()
    assert fetched is not None
    assert fetched.id == a.id  # ORDER BY created_at ASC LIMIT 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_repositories_masters_singleton.py -v`
Expected: FAIL (AttributeError: 'MasterRepository' object has no attribute 'get_singleton').

- [ ] **Step 3: Add `get_singleton` to `src/repositories/masters.py`**

Insert after the existing `get_by_tg_id` method (before `create`):

```python
    async def get_singleton(self) -> Master | None:
        """Return the single master of v0.1.

        If the invariant is violated, return the earliest-created row so the
        choice is deterministic. v0.2 (multi-tenant) will replace this with a
        short_id lookup.
        """
        stmt = select(Master).order_by(Master.created_at).limit(1)
        return cast(Master | None, await self._session.scalar(stmt))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_repositories_masters_singleton.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/repositories/masters.py tests/test_repositories_masters_singleton.py
git commit -m "feat(repo): MasterRepository.get_singleton for v0.1 one-master lookup"
```

---

## Task 3: `ClientRepository` — `get` + `upsert_by_phone`

**Files:**
- Create: `src/repositories/clients.py`
- Test: `tests/test_repositories_clients.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_repositories_clients.py`:

```python
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.repositories.clients import ClientRepository


async def _seed_master(session: AsyncSession, tg_id: int = 5001) -> Master:
    master = Master(tg_id=tg_id, name="Мастер")
    session.add(master)
    await session.flush()
    return master


@pytest.mark.asyncio
async def test_get_returns_none_when_absent(session: AsyncSession) -> None:
    repo = ClientRepository(session)
    assert await repo.get(uuid4()) is None


@pytest.mark.asyncio
async def test_upsert_inserts_new_client(session: AsyncSession) -> None:
    master = await _seed_master(session)
    await session.commit()

    repo = ClientRepository(session)
    client = await repo.upsert_by_phone(
        master_id=master.id, phone="+37499111222", name="Аня", tg_id=42
    )
    await session.commit()

    assert client.id is not None
    assert client.name == "Аня"
    assert client.phone == "+37499111222"
    assert client.tg_id == 42
    assert client.master_id == master.id


@pytest.mark.asyncio
async def test_upsert_updates_name_and_tg_id(session: AsyncSession) -> None:
    master = await _seed_master(session)
    await session.commit()

    repo = ClientRepository(session)
    first = await repo.upsert_by_phone(
        master_id=master.id, phone="+37499111222", name="Старое имя", tg_id=None
    )
    await session.commit()

    second = await repo.upsert_by_phone(
        master_id=master.id, phone="+37499111222", name="Новое имя", tg_id=99
    )
    await session.commit()

    assert second.id == first.id
    assert second.name == "Новое имя"
    assert second.tg_id == 99


@pytest.mark.asyncio
async def test_upsert_scoped_by_master(session: AsyncSession) -> None:
    master_a = await _seed_master(session, tg_id=7001)
    master_b = await _seed_master(session, tg_id=7002)
    await session.commit()

    repo = ClientRepository(session)
    a = await repo.upsert_by_phone(
        master_id=master_a.id, phone="+37499000000", name="A", tg_id=None
    )
    b = await repo.upsert_by_phone(
        master_id=master_b.id, phone="+37499000000", name="B", tg_id=None
    )
    await session.commit()

    assert a.id != b.id
    assert a.master_id == master_a.id
    assert b.master_id == master_b.id


@pytest.mark.asyncio
async def test_upsert_does_not_overwrite_tg_id_with_none(session: AsyncSession) -> None:
    master = await _seed_master(session)
    await session.commit()

    repo = ClientRepository(session)
    await repo.upsert_by_phone(
        master_id=master.id, phone="+37499111222", name="Х", tg_id=555
    )
    await session.commit()

    updated = await repo.upsert_by_phone(
        master_id=master.id, phone="+37499111222", name="Х", tg_id=None
    )
    await session.commit()

    assert updated.tg_id == 555
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_repositories_clients.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'src.repositories.clients').

- [ ] **Step 3: Implement `src/repositories/clients.py`**

```python
from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client


class ClientRepository:
    """CRUD for Client scoped by (master_id, phone) uniqueness."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, client_id: UUID) -> Client | None:
        return cast(Client | None, await self._session.get(Client, client_id))

    async def upsert_by_phone(
        self,
        *,
        master_id: UUID,
        phone: str,
        name: str,
        tg_id: int | None,
    ) -> Client:
        """Find existing (master_id, phone) row or create one.

        Updates `name` and `tg_id` if the row exists; `tg_id=None` does NOT
        overwrite an existing value (so a later anonymous booking by phone
        doesn't forget the Telegram linkage).
        """
        stmt = select(Client).where(
            Client.master_id == master_id, Client.phone == phone
        )
        existing = await self._session.scalar(stmt)
        if existing is None:
            client = Client(master_id=master_id, phone=phone, name=name, tg_id=tg_id)
            self._session.add(client)
            await self._session.flush()
            return client
        existing.name = name
        if tg_id is not None:
            existing.tg_id = tg_id
        return existing
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_repositories_clients.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/repositories/clients.py tests/test_repositories_clients.py
git commit -m "feat(repo): ClientRepository.upsert_by_phone with sticky tg_id"
```

---

## Task 4: `AppointmentRepository` — `list_active_for_month` + `list_for_client`

**Files:**
- Modify: `src/repositories/appointments.py`
- Test: `tests/test_repositories_appointments_epic4.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_repositories_appointments_epic4.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master, Service
from src.repositories.appointments import AppointmentRepository


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(tg_id=8001, name="М")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="К", phone="+37499111111")
    session.add(client)
    service = Service(master_id=master.id, name="Услуга", duration_min=60)
    session.add(service)
    await session.flush()
    return master, client, service


@pytest.mark.asyncio
async def test_list_active_for_month_empty(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    await session.commit()

    repo = AppointmentRepository(session)
    start = datetime(2026, 5, 1, tzinfo=UTC)
    end = datetime(2026, 6, 1, tzinfo=UTC)
    assert await repo.list_active_for_month(master.id, month_start_utc=start, month_end_utc=end) == []


@pytest.mark.asyncio
async def test_list_active_for_month_filters_range_and_status(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)

    def mk(start: datetime, status: str) -> None:
        session.add_all([])  # noqa: no-op to keep formatting tidy

    in_range = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 10, 8, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 10, 9, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    pending = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 12, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 12, 11, 0, tzinfo=UTC),
        status="pending", source="client_request",
    )
    cancelled = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 15, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 15, 11, 0, tzinfo=UTC),
        status="cancelled", source="client_request",
    )
    before = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 4, 28, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 28, 11, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    after = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 6, 3, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 6, 3, 11, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    await session.commit()

    result = await repo.list_active_for_month(
        master.id,
        month_start_utc=datetime(2026, 5, 1, tzinfo=UTC),
        month_end_utc=datetime(2026, 6, 1, tzinfo=UTC),
    )
    ids = {a.id for a in result}
    assert ids == {in_range.id, pending.id}
    assert cancelled.id not in ids
    assert before.id not in ids
    assert after.id not in ids


@pytest.mark.asyncio
async def test_list_for_client_orders_desc_and_excludes_pending(
    session: AsyncSession,
) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)

    older = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    newer = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 1, 11, 0, tzinfo=UTC),
        status="cancelled", source="client_request",
    )
    still_pending = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 1, 11, 0, tzinfo=UTC),
        status="pending", source="client_request",
    )
    await session.commit()

    result = await repo.list_for_client(master.id, client.id, limit=10)
    ids = [a.id for a in result]
    assert ids == [newer.id, older.id]  # DESC by start_at
    assert still_pending.id not in ids


@pytest.mark.asyncio
async def test_list_for_client_respects_limit(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)

    for i in range(5):
        await repo.create(
            master_id=master.id, client_id=client.id, service_id=service.id,
            start_at=datetime(2026, 1, i + 1, 10, 0, tzinfo=UTC),
            end_at=datetime(2026, 1, i + 1, 11, 0, tzinfo=UTC),
            status="confirmed", source="client_request",
        )
    await session.commit()

    result = await repo.list_for_client(master.id, client.id, limit=3)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_list_for_client_scoped_by_master(session: AsyncSession) -> None:
    master_a, client_a, service_a = await _seed(session)
    master_b = Master(tg_id=8002, name="Другой")
    session.add(master_b)
    await session.flush()
    service_b = Service(master_id=master_b.id, name="Услуга", duration_min=60)
    session.add(service_b)
    # Same client phone, different master:
    client_b = Client(master_id=master_b.id, name="Тот же", phone=client_a.phone)
    session.add(client_b)
    await session.flush()

    repo = AppointmentRepository(session)
    await repo.create(
        master_id=master_b.id, client_id=client_b.id, service_id=service_b.id,
        start_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 1, 1, 11, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    await session.commit()

    # Querying master_a / client_a returns nothing — the appointment belongs to master_b.
    result = await repo.list_for_client(master_a.id, client_a.id, limit=10)
    assert result == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_repositories_appointments_epic4.py -v`
Expected: FAIL (AttributeError: no attribute 'list_active_for_month' or 'list_for_client').

- [ ] **Step 3: Add both methods to `src/repositories/appointments.py`**

Append inside the `AppointmentRepository` class (after `list_active_for_day`):

```python
    async def list_active_for_month(
        self,
        master_id: UUID,
        *,
        month_start_utc: datetime,
        month_end_utc: datetime,
    ) -> list[Appointment]:
        """pending + confirmed appointments whose start_at lies in [month_start, month_end) UTC."""
        stmt = (
            select(Appointment)
            .where(
                Appointment.master_id == master_id,
                Appointment.status.in_(["pending", "confirmed"]),
                Appointment.start_at >= month_start_utc,
                Appointment.start_at < month_end_utc,
            )
            .order_by(Appointment.start_at)
        )
        return list((await self._session.scalars(stmt)).all())

    async def list_for_client(
        self,
        master_id: UUID,
        client_id: UUID,
        *,
        limit: int = 10,
        exclude_statuses: tuple[str, ...] = ("pending",),
    ) -> list[Appointment]:
        """Master-scoped history for one client, newest first, skipping pending by default."""
        stmt = (
            select(Appointment)
            .where(
                Appointment.master_id == master_id,
                Appointment.client_id == client_id,
            )
            .order_by(Appointment.start_at.desc())
            .limit(limit)
        )
        if exclude_statuses:
            stmt = stmt.where(Appointment.status.notin_(exclude_statuses))
        return list((await self._session.scalars(stmt)).all())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_repositories_appointments_epic4.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/repositories/appointments.py tests/test_repositories_appointments_epic4.py
git commit -m "feat(repo): list_active_for_month + list_for_client for calendar and history"
```

---

## Task 5: `availability.calculate_day_loads` — pure function

**Files:**
- Modify: `src/services/availability.py`
- Test: `tests/test_availability_day_loads.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_availability_day_loads.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.services.availability import calculate_day_loads

YEREVAN = ZoneInfo("Asia/Yerevan")


def test_off_day_yields_off_sentinel() -> None:
    result = calculate_day_loads(
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        booked_by_day={},
        month=date(2026, 5, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 4, 1, 0, 0, tzinfo=YEREVAN),
    )
    # May 1 2026 is Friday — no work_hours key → off.
    assert result[date(2026, 5, 1)] == -1
    # May 4 2026 is Monday — 9 slots of 60 min.
    assert result[date(2026, 5, 4)] == 9


def test_past_day_returns_off() -> None:
    result = calculate_day_loads(
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        booked_by_day={},
        month=date(2026, 5, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 5, 10, 12, 0, tzinfo=YEREVAN),
    )
    # Monday May 4 is in the past relative to May 10.
    assert result[date(2026, 5, 4)] == -1
    # Monday May 11 is future — 9 free slots.
    assert result[date(2026, 5, 11)] == 9


def test_today_filters_past_slots() -> None:
    result = calculate_day_loads(
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        booked_by_day={},
        month=date(2026, 5, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 5, 11, 14, 30, tzinfo=YEREVAN),
    )
    # Today (Mon May 11): slots 10,11,12,13,14 are gone; 15,16,17,18 remain = 4 slots.
    assert result[date(2026, 5, 11)] == 4


def test_booked_windows_reduce_count() -> None:
    import datetime as dt_mod

    booked = {
        date(2026, 5, 4): [
            (
                datetime(2026, 5, 4, 10, 0, tzinfo=YEREVAN),
                datetime(2026, 5, 4, 11, 0, tzinfo=YEREVAN),
            ),
            (
                datetime(2026, 5, 4, 15, 0, tzinfo=YEREVAN),
                datetime(2026, 5, 4, 16, 0, tzinfo=YEREVAN),
            ),
        ]
    }
    result = calculate_day_loads(
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        booked_by_day=booked,
        month=date(2026, 5, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 4, 1, 0, 0, tzinfo=YEREVAN),
    )
    # 9 total - 2 booked hours = 7.
    assert result[date(2026, 5, 4)] == 7
    _ = dt_mod  # silence unused import warning if any


def test_returns_all_days_of_month() -> None:
    result = calculate_day_loads(
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        booked_by_day={},
        month=date(2026, 2, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 1, 1, 0, 0, tzinfo=YEREVAN),
    )
    # Feb 2026 has 28 days.
    assert len(result) == 28
    assert min(result.keys()) == date(2026, 2, 1)
    assert max(result.keys()) == date(2026, 2, 28)


def test_month_with_31_days() -> None:
    result = calculate_day_loads(
        work_hours={},
        breaks={},
        booked_by_day={},
        month=date(2026, 3, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 1, 1, 0, 0, tzinfo=YEREVAN),
    )
    assert len(result) == 31
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_availability_day_loads.py -v`
Expected: FAIL (ImportError: cannot import name 'calculate_day_loads').

- [ ] **Step 3: Add `calculate_day_loads` to `src/services/availability.py`**

Append at the end of the file, below `calculate_free_slots`:

```python
from calendar import monthrange  # keep this import at the top of the file in practice


def calculate_day_loads(
    *,
    work_hours: dict[str, list[list[str]]],
    breaks: dict[str, list[list[str]]],
    booked_by_day: dict[date, list[tuple[datetime, datetime]]],
    month: date,
    tz: ZoneInfo,
    slot_step_min: int,
    service_duration_min: int,
    now: datetime,
) -> dict[date, int]:
    """Count free slots for every day of `month`.

    Returns {date: count} where count is:
      -1 — day is off (no work_hours for that weekday) or entirely in the past.
      0  — fully booked.
      N  — N free slots of the requested duration still fit that day.

    Pure: reuses `calculate_free_slots` per day; `booked_by_day` pre-groups
    appointments by local date so callers don't have to re-partition them.
    """
    _, days_in_month = monthrange(month.year, month.month)
    now_date = now.astimezone(tz).date()

    result: dict[date, int] = {}
    for day_num in range(1, days_in_month + 1):
        d = date(month.year, month.month, day_num)
        if d < now_date:
            result[d] = -1
            continue
        weekday = WEEKDAYS[d.weekday()]
        if not work_hours.get(weekday):
            result[d] = -1
            continue
        slots = calculate_free_slots(
            work_hours=work_hours,
            breaks=breaks,
            booked=booked_by_day.get(d, []),
            day=d,
            tz=tz,
            slot_step_min=slot_step_min,
            service_duration_min=service_duration_min,
            now=now if d == now_date else None,
        )
        result[d] = len(slots)
    return result
```

Also ensure `from calendar import monthrange` is at the top of the file next to the other imports (move it up from the snippet above).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_availability_day_loads.py -v`
Expected: 6 passed.

- [ ] **Step 5: Check 100% coverage still holds**

Run: `pytest tests/test_availability.py tests/test_availability_day_loads.py --cov=src/services/availability --cov-report=term-missing`
Expected: 100% coverage.

- [ ] **Step 6: Commit**

```bash
git add src/services/availability.py tests/test_availability_day_loads.py
git commit -m "feat(availability): calculate_day_loads for month calendar rendering"
```

---

## Task 6: `BookingService.get_month_load` + `list_client_history`

**Files:**
- Modify: `src/services/booking.py`
- Test: `tests/test_services_booking_epic4.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_services_booking_epic4.py`:

```python
from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master, Service
from src.services.booking import BookingService

YEREVAN = ZoneInfo("Asia/Yerevan")


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=6001, name="М",
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={}, slot_step_min=60, timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="К", phone="+37499555555")
    session.add(client)
    service = Service(master_id=master.id, name="Услуга", duration_min=60)
    session.add(service)
    await session.flush()
    return master, client, service


@pytest.mark.asyncio
async def test_get_month_load_empty_calendar(session: AsyncSession) -> None:
    master, _, service = await _seed(session)
    await session.commit()

    svc = BookingService(session)
    now = datetime(2026, 4, 1, 0, 0, tzinfo=YEREVAN)
    loads = await svc.get_month_load(master=master, service=service, month=date(2026, 5, 1), now=now)

    # May 2026: Mondays are 4, 11, 18, 25 → 9 free slots each. Other days -1.
    assert loads[date(2026, 5, 4)] == 9
    assert loads[date(2026, 5, 11)] == 9
    assert loads[date(2026, 5, 1)] == -1


@pytest.mark.asyncio
async def test_get_month_load_subtracts_existing_bookings(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    from src.repositories.appointments import AppointmentRepository

    repo = AppointmentRepository(session)
    # Mon 2026-05-04 10:00-11:00 Yerevan = 06:00-07:00 UTC
    await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 6, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    await session.commit()

    svc = BookingService(session)
    loads = await svc.get_month_load(
        master=master, service=service, month=date(2026, 5, 1),
        now=datetime(2026, 4, 1, 0, 0, tzinfo=YEREVAN),
    )
    assert loads[date(2026, 5, 4)] == 8  # 9 - 1 booked


@pytest.mark.asyncio
async def test_list_client_history_delegates_to_repo(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    from src.repositories.appointments import AppointmentRepository

    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 3, 1, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 1, 8, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    await session.commit()

    svc = BookingService(session)
    history = await svc.list_client_history(master, client.id, limit=10)
    assert [a.id for a in history] == [appt.id]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_services_booking_epic4.py -v`
Expected: FAIL (AttributeError: 'BookingService' object has no attribute 'get_month_load').

- [ ] **Step 3: Add both methods to `src/services/booking.py`**

Add to imports at the top:

```python
from calendar import monthrange
from collections import defaultdict

from src.services.availability import calculate_day_loads, calculate_free_slots
```

(Replace the existing `from src.services.availability import calculate_free_slots` line.)

Append inside the `BookingService` class:

```python
    async def get_month_load(
        self,
        *,
        master: Master,
        service: Service,
        month: date,
        now: datetime | None = None,
    ) -> dict[date, int]:
        """Return free-slot counts per day of `month` (see calculate_day_loads)."""
        n = now if now is not None else now_utc()
        tz = ZoneInfo(master.timezone)
        _, days_in_month = monthrange(month.year, month.month)
        month_start_local = datetime(month.year, month.month, 1, tzinfo=tz)
        month_end_local = datetime(
            month.year + (month.month // 12),
            (month.month % 12) + 1,
            1,
            tzinfo=tz,
        )
        month_start_utc = month_start_local.astimezone(UTC)
        month_end_utc = month_end_local.astimezone(UTC)

        appts = await self._repo.list_active_for_month(
            master.id,
            month_start_utc=month_start_utc,
            month_end_utc=month_end_utc,
        )

        booked_by_day: dict[date, list[tuple[datetime, datetime]]] = defaultdict(list)
        for a in appts:
            local_day = a.start_at.astimezone(tz).date()
            booked_by_day[local_day].append((a.start_at, a.end_at))

        return calculate_day_loads(
            work_hours=master.work_hours,
            breaks=master.breaks,
            booked_by_day=dict(booked_by_day),
            month=month,
            tz=tz,
            slot_step_min=master.slot_step_min,
            service_duration_min=service.duration_min,
            now=n,
        )

    async def list_client_history(
        self,
        master: Master,
        client_id: UUID,
        *,
        limit: int = 10,
    ) -> list[Appointment]:
        """Master-scoped recent history for a client (excludes pending)."""
        return await self._repo.list_for_client(master.id, client_id, limit=limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_services_booking_epic4.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/services/booking.py tests/test_services_booking_epic4.py
git commit -m "feat(booking): get_month_load + list_client_history"
```

---

## Task 7: Callback data classes

**Files:**
- Create: `src/callback_data/calendar.py`
- Create: `src/callback_data/slots.py`
- Create: `src/callback_data/approval.py`
- Create: `src/callback_data/client_services.py`
- Test: `tests/test_callback_data_epic4.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_callback_data_epic4.py`:

```python
from __future__ import annotations

from uuid import uuid4

from src.callback_data.approval import ApprovalCallback
from src.callback_data.calendar import CalendarCallback
from src.callback_data.client_services import ClientServicePick
from src.callback_data.slots import SlotCallback


def test_calendar_pack_roundtrip() -> None:
    cb = CalendarCallback(action="pick", year=2026, month=5, day=11)
    packed = cb.pack()
    assert len(packed) <= 64
    restored = CalendarCallback.unpack(packed)
    assert restored == cb


def test_calendar_nav_uses_day_zero() -> None:
    cb = CalendarCallback(action="nav", year=2026, month=6, day=0)
    restored = CalendarCallback.unpack(cb.pack())
    assert restored.action == "nav"
    assert restored.day == 0


def test_slot_pack_roundtrip() -> None:
    cb = SlotCallback(hour=14, minute=30)
    restored = SlotCallback.unpack(cb.pack())
    assert restored == cb


def test_approval_pack_roundtrip_within_64b() -> None:
    appt_id = uuid4()
    cb = ApprovalCallback(action="confirm", appointment_id=appt_id)
    packed = cb.pack()
    assert len(packed.encode("utf-8")) <= 64
    restored = ApprovalCallback.unpack(packed)
    assert restored == cb


def test_client_service_pack_roundtrip() -> None:
    svc_id = uuid4()
    cb = ClientServicePick(service_id=svc_id)
    restored = ClientServicePick.unpack(cb.pack())
    assert restored == cb
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_callback_data_epic4.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Create `src/callback_data/calendar.py`**

```python
from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class CalendarCallback(CallbackData, prefix="cal"):
    """Calendar cell / navigation button.

    action:
      - pick: user picked a concrete date (year, month, day).
      - nav: prev/next month (day=0, sign encoded in month: >0 go forward, <0 back).
      - noop: disabled cell (past day, empty grid slot). Handler ignores.
    """

    action: Literal["pick", "nav", "noop"]
    year: int
    month: int
    day: int = 0
```

- [ ] **Step 4: Create `src/callback_data/slots.py`**

```python
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class SlotCallback(CallbackData, prefix="slot"):
    hour: int
    minute: int
```

- [ ] **Step 5: Create `src/callback_data/approval.py`**

```python
from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class ApprovalCallback(CallbackData, prefix="appr"):
    action: Literal["confirm", "reject", "history"]
    appointment_id: UUID
```

- [ ] **Step 6: Create `src/callback_data/client_services.py`**

```python
from __future__ import annotations

from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class ClientServicePick(CallbackData, prefix="csvc"):
    service_id: UUID
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_callback_data_epic4.py -v`
Expected: 5 passed.

- [ ] **Step 8: Commit**

```bash
git add src/callback_data/calendar.py src/callback_data/slots.py \
        src/callback_data/approval.py src/callback_data/client_services.py \
        tests/test_callback_data_epic4.py
git commit -m "feat(cb): typed CallbackData for calendar, slot, approval, client service pick"
```

---

## Task 8: FSM `ClientBooking` + strings additions

**Files:**
- Create: `src/fsm/client_booking.py`
- Modify: `src/strings.py`

- [ ] **Step 1: Create `src/fsm/client_booking.py`**

```python
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ClientBooking(StatesGroup):
    ChoosingService = State()
    ChoosingDate = State()
    ChoosingTime = State()
    EnteringName = State()
    EnteringPhone = State()
    Confirming = State()
```

- [ ] **Step 2: Add string keys to `src/strings.py`**

Inside `_RU`, append before the closing brace (keep alphabetic grouping loose — match existing style):

```python
    # --- Epic 4: client booking ---
    "CLIENT_START_NO_MASTER": "Бот пока не настроен. Попросите мастера запустить его.",
    "CLIENT_CHOOSE_SERVICE": "Выберите услугу:",
    "CLIENT_NO_SERVICES": "У мастера пока нет услуг. Попробуйте позже.",
    "CLIENT_CHOOSE_DATE": "Выберите дату:",
    "CLIENT_CHOOSE_TIME": "Свободные слоты на {date}:",
    "CLIENT_NO_SLOTS": "На этот день свободных слотов нет. Выберите другую дату.",
    "CLIENT_ASK_NAME": "Как вас зовут?",
    "CLIENT_BAD_NAME": "Пожалуйста, введите имя (1–60 символов).",
    "CLIENT_ASK_PHONE": "Телефон в формате +374 XX XXX XXX:",
    "CLIENT_BAD_PHONE": "Не разобрал номер. Пример: +374 99 123 456",
    "CLIENT_CONFIRM_TITLE": (
        "📋 Проверьте запись:\n"
        "🧑\u200d⚕️ Услуга: {service}\n"
        "📅 {date} в {time}\n"
        "👤 {name}\n"
        "📞 {phone}\n\n"
        "Подтвердить?"
    ),
    "CLIENT_BTN_CONFIRM": "✅ Подтвердить",
    "CLIENT_BTN_CANCEL": "❌ Отменить",
    "CLIENT_BTN_BACK": "← Назад",
    "CLIENT_SENT": "Заявка отправлена мастеру. Ждите подтверждения.",
    "CLIENT_CANCELLED": "Запись отменена.",
    "CLIENT_SLOT_TAKEN": "Этот слот только что заняли. Выберите другое время.",
    "CLIENT_APPT_CONFIRMED": "Мастер подтвердил вашу запись на {date} в {time}. До встречи!",
    "CLIENT_APPT_REJECTED": "К сожалению, мастер отклонил запись на {date} в {time}.",
    # --- Epic 4: master approval ---
    "APPT_NOTIFY_MASTER": (
        "🔔 Новая заявка\n"
        "🧑 {name}\n"
        "📞 {phone}\n"
        "🧑\u200d⚕️ {service} ({duration} мин)\n"
        "📅 {date} в {time} ({weekday})"
    ),
    "APPT_BTN_CONFIRM": "✅ Подтвердить",
    "APPT_BTN_REJECT": "❌ Отклонить",
    "APPT_BTN_HISTORY": "📋 История клиента",
    "APPT_ALREADY_PROCESSED": "Эта заявка уже обработана.",
    "APPT_CONFIRMED_STAMP": "\n\n✅ Подтверждено в {time}",
    "APPT_REJECTED_STAMP": "\n\n❌ Отклонено в {time}",
    "APPT_HISTORY_TITLE": "История клиента {name} (последние {limit}):",
    "APPT_HISTORY_LINE": "• {date} {time} — {service} — {status}",
    "APPT_HISTORY_EMPTY": "У клиента пока нет истории записей.",
    "APPT_STATUS_CONFIRMED": "✅ подтверждено",
    "APPT_STATUS_CANCELLED": "❌ отменено",
    "APPT_STATUS_REJECTED": "❌ отклонено",
    "APPT_STATUS_COMPLETED": "☑️ завершено",
    "APPT_STATUS_NO_SHOW": "⚠️ не пришёл",
    "MONTH_NAMES": [
        "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
    ],
    "WEEKDAY_SHORT": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
```

Mirror the same keys into `_HY` with Armenian text (copy the RU values verbatim for now — HY is currently overridden to RU via `set_current_lang` anyway; translation is Epic 8). Keep the existing `WEEKDAYS` dict untouched — `WEEKDAY_SHORT` is a list indexed by `date.weekday()`.

- [ ] **Step 3: Run full test suite to catch stray issues**

Run: `pytest -q`
Expected: All existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add src/fsm/client_booking.py src/strings.py
git commit -m "feat(fsm,strings): ClientBooking states + RU strings for Epic 4"
```

---

## Task 9: `keyboards/calendar.py` — inline month with DayLoad coloring

**Files:**
- Create: `src/keyboards/calendar.py`
- Test: `tests/test_keyboards_calendar.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_keyboards_calendar.py`:

```python
from __future__ import annotations

from datetime import date

from src.callback_data.calendar import CalendarCallback
from src.keyboards.calendar import MAX_MONTHS_AHEAD, calendar_keyboard


def _all_buttons(kb) -> list:
    return [b for row in kb.inline_keyboard for b in row]


def _days(kb) -> list:
    return [b for b in _all_buttons(kb) if len(b.text) >= 1 and b.text[0] in "🟢🟡🔴⚫"]


def test_header_row_has_month_and_year() -> None:
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): -1 for d in range(1, 32)},
        today=date(2026, 4, 21),
    )
    header = kb.inline_keyboard[0]
    # 3 cells: [« prev] [Май 2026] [next »]
    assert len(header) == 3
    assert "Май 2026" in header[1].text


def test_weekday_header_row() -> None:
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): -1 for d in range(1, 32)},
        today=date(2026, 4, 21),
    )
    weekday_row = kb.inline_keyboard[1]
    labels = [b.text for b in weekday_row]
    assert labels == ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def test_day_cells_use_correct_emoji() -> None:
    loads = {date(2026, 5, d): -1 for d in range(1, 32)}
    loads[date(2026, 5, 4)] = 9   # 🟢 ≥5
    loads[date(2026, 5, 5)] = 3   # 🟡 1..4
    loads[date(2026, 5, 6)] = 0   # 🔴 0
    loads[date(2026, 5, 7)] = -1  # ⚫ off

    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads=loads,
        today=date(2026, 4, 21),
    )
    day_texts = {b.text for b in _days(kb)}
    assert any(t.startswith("🟢") and t.endswith("4") for t in day_texts)
    assert any(t.startswith("🟡") and t.endswith("5") for t in day_texts)
    assert any(t.startswith("🔴") and t.endswith("6") for t in day_texts)
    assert any(t.startswith("⚫") for t in day_texts)


def test_day_callback_packs_pick_action() -> None:
    loads = {date(2026, 5, d): 9 for d in range(1, 32)}
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads=loads,
        today=date(2026, 4, 21),
    )
    picked = next(
        b for b in _all_buttons(kb)
        if b.callback_data and b.callback_data.startswith("cal:pick")
    )
    restored = CalendarCallback.unpack(picked.callback_data)
    assert restored.action == "pick"
    assert restored.year == 2026
    assert restored.month == 5


def test_past_day_cells_are_noop() -> None:
    loads = {date(2026, 5, d): -1 for d in range(1, 32)}
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads=loads,
        today=date(2026, 5, 15),
    )
    for b in _days(kb):
        if b.callback_data and b.callback_data.startswith("cal:pick"):
            cb = CalendarCallback.unpack(b.callback_data)
            assert cb.day >= 15  # no picks in the past


def test_prev_disabled_when_at_current_month() -> None:
    loads = {date(2026, 5, d): -1 for d in range(1, 32)}
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads=loads,
        today=date(2026, 5, 21),
    )
    prev = kb.inline_keyboard[0][0]
    # 'noop' callback means disabled.
    assert CalendarCallback.unpack(prev.callback_data).action == "noop"


def test_next_disabled_at_max_lookahead() -> None:
    target_month = date(2026, 5, 1)
    today = date(2026, 5, 1)
    # Emulate already showing today + MAX_MONTHS_AHEAD ahead.
    far = date(target_month.year + (target_month.month + MAX_MONTHS_AHEAD - 1) // 12,
               ((target_month.month + MAX_MONTHS_AHEAD - 1) % 12) + 1, 1)
    loads = {date(far.year, far.month, d): -1 for d in range(1, 29)}
    kb = calendar_keyboard(month=far, loads=loads, today=today)
    nxt = kb.inline_keyboard[0][2]
    assert CalendarCallback.unpack(nxt.callback_data).action == "noop"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_keyboards_calendar.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `src/keyboards/calendar.py`**

```python
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.calendar import CalendarCallback
from src.strings import strings

DayLoad = Literal["off", "full", "tight", "free"]

MAX_MONTHS_AHEAD: int = 3  # client can navigate up to 3 months forward from today

_EMOJI: dict[DayLoad, str] = {"free": "🟢", "tight": "🟡", "full": "🔴", "off": "⚫"}


def _classify(count: int) -> DayLoad:
    if count < 0:
        return "off"
    if count == 0:
        return "full"
    if count < 5:
        return "tight"
    return "free"


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def _shift_month(d: date, by: int) -> date:
    total = d.year * 12 + (d.month - 1) + by
    return date(total // 12, (total % 12) + 1, 1)


def _noop_button(text: str, year: int, month: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=CalendarCallback(action="noop", year=year, month=month, day=0).pack(),
    )


def calendar_keyboard(
    *,
    month: date,
    loads: dict[date, int],
    today: date,
) -> InlineKeyboardMarkup:
    """Render a month grid with emoji-coded availability.

    `loads` must contain an entry for every day of `month`; -1 encodes "off",
    0 = full, 1..4 = tight, ≥5 = free. Past days render as ⚫ without a pick callback.
    """
    year, month_num = month.year, month.month
    month_name = strings.MONTH_NAMES[month_num - 1]

    prev_shift = _shift_month(month, -1)
    next_shift = _shift_month(month, +1)
    can_prev = _months_between(today.replace(day=1), prev_shift) >= 0
    can_next = _months_between(today.replace(day=1), next_shift) <= MAX_MONTHS_AHEAD

    prev_btn: InlineKeyboardButton
    if can_prev:
        prev_btn = InlineKeyboardButton(
            text="«",
            callback_data=CalendarCallback(
                action="nav", year=prev_shift.year, month=prev_shift.month, day=0
            ).pack(),
        )
    else:
        prev_btn = _noop_button(" ", year, month_num)

    next_btn: InlineKeyboardButton
    if can_next:
        next_btn = InlineKeyboardButton(
            text="»",
            callback_data=CalendarCallback(
                action="nav", year=next_shift.year, month=next_shift.month, day=0
            ).pack(),
        )
    else:
        next_btn = _noop_button(" ", year, month_num)

    header = [
        prev_btn,
        _noop_button(f"{month_name} {year}", year, month_num),
        next_btn,
    ]

    weekday_row = [
        _noop_button(label, year, month_num) for label in strings.WEEKDAY_SHORT
    ]

    rows: list[list[InlineKeyboardButton]] = [header, weekday_row]
    _, days_in_month = monthrange(year, month_num)
    first_weekday = date(year, month_num, 1).weekday()  # Mon=0..Sun=6

    cells: list[InlineKeyboardButton] = [
        _noop_button(" ", year, month_num) for _ in range(first_weekday)
    ]
    for day in range(1, days_in_month + 1):
        d = date(year, month_num, day)
        count = loads[d]
        load = _classify(count)
        emoji = _EMOJI[load]
        label = f"{emoji}{day}"
        if d < today or load == "off":
            cells.append(_noop_button(label, year, month_num))
        else:
            cells.append(
                InlineKeyboardButton(
                    text=label,
                    callback_data=CalendarCallback(
                        action="pick", year=year, month=month_num, day=day
                    ).pack(),
                )
            )

    # Pad trailing cells to fill the last row.
    while len(cells) % 7 != 0:
        cells.append(_noop_button(" ", year, month_num))

    for i in range(0, len(cells), 7):
        rows.append(cells[i : i + 7])

    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_keyboards_calendar.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/keyboards/calendar.py tests/test_keyboards_calendar.py
git commit -m "feat(keyboards): inline calendar with DayLoad coloring + bounded nav"
```

---

## Task 10: `keyboards/slots.py` — slots grid + confirm + services + approval keyboards

**Files:**
- Create: `src/keyboards/slots.py`
- Test: `tests/test_keyboards_slots.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_keyboards_slots.py`:

```python
from __future__ import annotations

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.callback_data.approval import ApprovalCallback
from src.callback_data.client_services import ClientServicePick
from src.callback_data.slots import SlotCallback
from src.db.models import Service
from src.keyboards.slots import approval_kb, confirm_kb, services_pick_kb, slots_grid

YEREVAN = ZoneInfo("Asia/Yerevan")


def test_slots_grid_three_per_row_with_hhmm_labels() -> None:
    slots = [
        datetime(2026, 5, 4, 10, 0, tzinfo=YEREVAN),
        datetime(2026, 5, 4, 11, 0, tzinfo=YEREVAN),
        datetime(2026, 5, 4, 12, 0, tzinfo=YEREVAN),
        datetime(2026, 5, 4, 13, 0, tzinfo=YEREVAN),
    ]
    kb = slots_grid(slots, tz=YEREVAN)
    # 2 rows of slots + 1 row for "back" = 3 rows.
    assert len(kb.inline_keyboard) == 3
    assert len(kb.inline_keyboard[0]) == 3
    assert len(kb.inline_keyboard[1]) == 1  # trailing row has only one slot
    assert kb.inline_keyboard[0][0].text == "10:00"
    restored = SlotCallback.unpack(kb.inline_keyboard[0][0].callback_data)
    assert (restored.hour, restored.minute) == (10, 0)
    # Last row is the back button.
    assert kb.inline_keyboard[-1][0].callback_data == "client_back"


def test_confirm_kb_has_confirm_and_cancel() -> None:
    kb = confirm_kb()
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert "✅ Подтвердить" in texts
    assert "❌ Отменить" in texts


def test_services_pick_kb_packs_service_ids() -> None:
    s1 = Service(id=uuid4(), master_id=uuid4(), name="Стрижка", duration_min=60)
    s2 = Service(id=uuid4(), master_id=uuid4(), name="Маникюр", duration_min=45)
    kb = services_pick_kb([s1, s2])
    assert len(kb.inline_keyboard) == 2
    first = kb.inline_keyboard[0][0]
    restored = ClientServicePick.unpack(first.callback_data)
    assert restored.service_id == s1.id
    assert "Стрижка" in first.text
    assert "60" in first.text


def test_approval_kb_has_three_buttons() -> None:
    appt_id = uuid4()
    kb = approval_kb(appt_id)
    buttons = [b for row in kb.inline_keyboard for b in row]
    actions = set()
    for b in buttons:
        actions.add(ApprovalCallback.unpack(b.callback_data).action)
    assert actions == {"confirm", "reject", "history"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_keyboards_slots.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `src/keyboards/slots.py`**

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.approval import ApprovalCallback
from src.callback_data.client_services import ClientServicePick
from src.callback_data.slots import SlotCallback
from src.db.models import Service
from src.strings import strings


def slots_grid(slots: list[datetime], *, tz: ZoneInfo) -> InlineKeyboardMarkup:
    """Render 3-per-row HH:MM buttons, plus a trailing Back row."""
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []
    for slot in slots:
        local = slot.astimezone(tz)
        current.append(
            InlineKeyboardButton(
                text=f"{local.hour:02d}:{local.minute:02d}",
                callback_data=SlotCallback(hour=local.hour, minute=local.minute).pack(),
            )
        )
        if len(current) == 3:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append(
        [InlineKeyboardButton(text=strings.CLIENT_BTN_BACK, callback_data="client_back")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.CLIENT_BTN_CONFIRM, callback_data="client_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.CLIENT_BTN_CANCEL, callback_data="client_cancel"
                )
            ],
        ]
    )


def services_pick_kb(services: list[Service]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for svc in services:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{svc.name} · {svc.duration_min} мин",
                    callback_data=ClientServicePick(service_id=svc.id).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def approval_kb(appointment_id: UUID) -> InlineKeyboardMarkup:
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
            [
                InlineKeyboardButton(
                    text=strings.APPT_BTN_HISTORY,
                    callback_data=ApprovalCallback(
                        action="history", appointment_id=appointment_id
                    ).pack(),
                )
            ],
        ]
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_keyboards_slots.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/keyboards/slots.py tests/test_keyboards_slots.py
git commit -m "feat(keyboards): slots grid, confirm, services pick, approval keyboards"
```

---

## Task 11: Client handlers — `/start`, service pick, calendar render, date pick

**Files:**
- Create: `src/handlers/client/__init__.py`
- Create: `src/handlers/client/start.py`
- Create: `src/handlers/client/booking.py`
- Test: `tests/test_handlers_client_booking.py` (partial — extended in Task 12)

- [ ] **Step 1: Write the failing test**

Create `tests/test_handlers_client_booking.py` (first portion — later tasks append more tests):

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.calendar import CalendarCallback
from src.callback_data.client_services import ClientServicePick
from src.db.models import Master, Service
from src.fsm.client_booking import ClientBooking
from src.handlers.client.booking import (
    handle_date_pick,
    handle_service_pick,
)
from src.handlers.client.start import handle_start


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMsg:
    from_user: _FakeUser | None = None
    answers: list[tuple[str, Any]] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.answers.append((text, reply_markup))


@dataclass
class _FakeCallback:
    data: str
    from_user: _FakeUser
    message: _FakeMsg
    answered: list[Any] = field(default_factory=list)

    async def answer(self, *args: Any, **kwargs: Any) -> None:
        self.answered.append((args, kwargs))


def _make_fsm(tg_id: int) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=tg_id, user_id=tg_id),
    )


@pytest.mark.asyncio
async def test_start_no_master_replies_with_stub(session: AsyncSession) -> None:
    msg = _FakeMsg(from_user=_FakeUser(id=123))
    state = _make_fsm(123)

    await handle_start(msg, master=None, state=state, session=session)

    assert msg.answers
    text, _ = msg.answers[0]
    assert "не настроен" in text


@pytest.mark.asyncio
async def test_start_with_master_via_singleton_shows_services(
    session: AsyncSession,
) -> None:
    master = Master(tg_id=7777, name="Мастер")
    session.add(master)
    await session.flush()
    session.add(Service(master_id=master.id, name="Стрижка", duration_min=60))
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=42))  # tg_id != master.tg_id → client path
    state = _make_fsm(42)

    await handle_start(msg, master=None, state=state, session=session)

    assert msg.answers
    text, kb = msg.answers[-1]
    assert "услугу" in text.lower()
    assert kb is not None  # services_pick_kb with one row
    current = await state.get_state()
    assert current == ClientBooking.ChoosingService.state


@pytest.mark.asyncio
async def test_start_with_empty_services_shows_no_services(
    session: AsyncSession,
) -> None:
    master = Master(tg_id=7778, name="Мастер")
    session.add(master)
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=43))
    state = _make_fsm(43)

    await handle_start(msg, master=None, state=state, session=session)

    text, _ = msg.answers[-1]
    assert "услуг" in text.lower()


@pytest.mark.asyncio
async def test_service_pick_saves_id_and_renders_calendar(
    session: AsyncSession,
) -> None:
    master = Master(
        tg_id=9000, name="М",
        work_hours={"mon": [["10:00", "19:00"]]}, breaks={},
        slot_step_min=60, timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=55))
    cb = _FakeCallback(
        data=ClientServicePick(service_id=service.id).pack(),
        from_user=_FakeUser(id=55),
        message=msg,
    )
    state = _make_fsm(55)
    await state.set_state(ClientBooking.ChoosingService)

    cb_data = ClientServicePick(service_id=service.id)
    await handle_service_pick(cb, callback_data=cb_data, state=state, session=session)

    assert await state.get_state() == ClientBooking.ChoosingDate.state
    data = await state.get_data()
    assert data["service_id"] == str(service.id)
    # Calendar rendered in msg.answers
    assert msg.answers
    _, kb = msg.answers[-1]
    assert kb is not None


@pytest.mark.asyncio
async def test_date_pick_renders_slots_or_no_slots(session: AsyncSession) -> None:
    master = Master(
        tg_id=9001, name="М",
        work_hours={"mon": [["10:00", "19:00"]]}, breaks={},
        slot_step_min=60, timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=66))
    # Monday 2026-05-04 — work day; handler will compute free slots.
    cb = _FakeCallback(
        data=CalendarCallback(action="pick", year=2026, month=5, day=4).pack(),
        from_user=_FakeUser(id=66),
        message=msg,
    )
    state = _make_fsm(66)
    await state.set_state(ClientBooking.ChoosingDate)
    await state.update_data(service_id=str(service.id))

    cb_data = CalendarCallback(action="pick", year=2026, month=5, day=4)
    await handle_date_pick(cb, callback_data=cb_data, state=state, session=session)

    assert await state.get_state() == ClientBooking.ChoosingTime.state
    data = await state.get_data()
    assert data["date"] == "2026-05-04"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_handlers_client_booking.py -v`
Expected: FAIL (ModuleNotFoundError: src.handlers.client).

- [ ] **Step 3: Create `src/handlers/client/__init__.py`**

```python
from __future__ import annotations

from aiogram import Router

from src.handlers.client.booking import router as booking_router
from src.handlers.client.start import router as start_router

router = Router(name="client")
router.include_router(start_router)
router.include_router(booking_router)

__all__ = ["router"]
```

- [ ] **Step 4: Create `src/handlers/client/start.py`**

```python
from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.fsm.client_booking import ClientBooking
from src.keyboards.slots import services_pick_kb
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.strings import strings

router = Router(name="client_start")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


@router.message(CommandStart())
async def handle_start(
    message: Message,
    master: Master | None,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Entry point for any user whose tg_id is not the master's.

    The master's own `/start` is handled by `handlers/master/start.py` which runs
    before this router (master router is registered first). When this handler runs,
    `master` middleware value is always None by construction.
    """
    if master is not None:
        return  # master router should have caught it

    m_repo = MasterRepository(session)
    the_master = await m_repo.get_singleton()
    if the_master is None:
        await message.answer(strings.CLIENT_START_NO_MASTER)
        return

    s_repo = ServiceRepository(session)
    services = await s_repo.list_active(the_master.id)
    if not services:
        await message.answer(strings.CLIENT_NO_SERVICES)
        return

    await state.clear()
    await state.set_state(ClientBooking.ChoosingService)
    await state.update_data(master_id=str(the_master.id))
    await message.answer(strings.CLIENT_CHOOSE_SERVICE, reply_markup=services_pick_kb(services))
    log.info("client_start", tg_id=message.from_user.id if message.from_user else None)


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(strings.CLIENT_CANCELLED)
```

- [ ] **Step 5: Create `src/handlers/client/booking.py` (initial — service + date pickers)**

```python
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.calendar import CalendarCallback
from src.callback_data.client_services import ClientServicePick
from src.fsm.client_booking import ClientBooking
from src.keyboards.calendar import calendar_keyboard
from src.keyboards.slots import slots_grid
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.strings import strings
from src.utils.time import now_utc

router = Router(name="client_booking")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


async def _load_master_service(
    session: AsyncSession, master_id: UUID, service_id: UUID
):
    m_repo = MasterRepository(session)
    s_repo = ServiceRepository(session)
    master = await m_repo.get_singleton()
    if master is None or master.id != master_id:
        return None, None
    service = await s_repo.get(service_id, master_id=master_id)
    return master, service


async def _render_calendar(
    *,
    target: Any,  # Message or CallbackQuery.message
    master,
    service,
    state: FSMContext,
    session: AsyncSession,
    month: date | None = None,
) -> None:
    now = now_utc()
    tz = ZoneInfo(master.timezone)
    today = now.astimezone(tz).date()
    the_month = month or today.replace(day=1)

    svc = BookingService(session)
    loads = await svc.get_month_load(master=master, service=service, month=the_month, now=now)

    await target.answer(
        strings.CLIENT_CHOOSE_DATE,
        reply_markup=calendar_keyboard(month=the_month, loads=loads, today=today),
    )
    await state.set_state(ClientBooking.ChoosingDate)


@router.callback_query(ClientServicePick.filter(), ClientBooking.ChoosingService)
async def handle_service_pick(
    callback: CallbackQuery,
    callback_data: ClientServicePick,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    master_id = UUID(data["master_id"])
    master, service = await _load_master_service(session, master_id, callback_data.service_id)
    if master is None or service is None:
        await callback.answer(strings.CLIENT_NO_SERVICES, show_alert=True)
        await state.clear()
        return

    await state.update_data(service_id=str(service.id))
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await _render_calendar(
            target=callback.message, master=master, service=service,
            state=state, session=session,
        )


@router.callback_query(CalendarCallback.filter(), ClientBooking.ChoosingDate)
async def handle_date_pick(
    callback: CallbackQuery,
    callback_data: CalendarCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback_data.action == "noop":
        await callback.answer()
        return

    data = await state.get_data()
    master_id = UUID(data["master_id"])
    service_id = UUID(data["service_id"])
    master, service = await _load_master_service(session, master_id, service_id)
    if master is None or service is None:
        await callback.answer(strings.CLIENT_NO_SERVICES, show_alert=True)
        await state.clear()
        return

    if callback_data.action == "nav":
        await callback.answer()
        if callback.message is not None and hasattr(callback.message, "answer"):
            await _render_calendar(
                target=callback.message, master=master, service=service,
                state=state, session=session,
                month=date(callback_data.year, callback_data.month, 1),
            )
        return

    # action == "pick"
    picked = date(callback_data.year, callback_data.month, callback_data.day)
    tz = ZoneInfo(master.timezone)
    svc = BookingService(session)
    slots = await svc.get_free_slots(master, service, picked, now=now_utc())

    await callback.answer()
    if callback.message is None or not hasattr(callback.message, "answer"):
        return

    if not slots:
        await callback.message.answer(strings.CLIENT_NO_SLOTS)
        # Stay in ChoosingDate; re-render the calendar.
        await _render_calendar(
            target=callback.message, master=master, service=service,
            state=state, session=session,
            month=picked.replace(day=1),
        )
        return

    await state.update_data(date=picked.isoformat())
    await state.set_state(ClientBooking.ChoosingTime)
    await callback.message.answer(
        strings.CLIENT_CHOOSE_TIME.format(date=picked.strftime("%d.%m.%Y")),
        reply_markup=slots_grid(slots, tz=tz),
    )
```

Note: `Any` import at the top — add `from typing import Any` alongside the existing imports.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_handlers_client_booking.py -v`
Expected: 5 passed.

- [ ] **Step 7: Commit**

```bash
git add src/handlers/client/ tests/test_handlers_client_booking.py
git commit -m "feat(handlers): client /start + service pick + calendar date pick"
```

---

## Task 12: Client handlers — time pick, name, phone, confirm

**Files:**
- Modify: `src/handlers/client/booking.py`
- Test: `tests/test_handlers_client_booking.py` (extend)

- [ ] **Step 1: Append tests to `tests/test_handlers_client_booking.py`**

Append these imports at the top (if missing):

```python
from datetime import UTC, datetime, timedelta
from src.callback_data.slots import SlotCallback
from src.db.models import Appointment
from src.exceptions import SlotAlreadyTaken
```

Append these tests at the end of the file:

```python
@pytest.mark.asyncio
async def test_time_pick_saves_start_and_asks_name(session: AsyncSession) -> None:
    master = Master(
        tg_id=9100, name="М",
        work_hours={"mon": [["10:00", "19:00"]]}, breaks={},
        slot_step_min=60, timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    from src.handlers.client.booking import handle_time_pick
    msg = _FakeMsg(from_user=_FakeUser(id=77))
    cb = _FakeCallback(
        data=SlotCallback(hour=14, minute=0).pack(),
        from_user=_FakeUser(id=77),
        message=msg,
    )
    state = _make_fsm(77)
    await state.set_state(ClientBooking.ChoosingTime)
    await state.update_data(
        master_id=str(master.id),
        service_id=str(service.id),
        date="2026-05-04",
    )

    cb_data = SlotCallback(hour=14, minute=0)
    await handle_time_pick(cb, callback_data=cb_data, state=state, session=session)

    assert await state.get_state() == ClientBooking.EnteringName.state
    data = await state.get_data()
    assert data["start_at"].startswith("2026-05-04T")
    assert msg.answers
    text, _ = msg.answers[-1]
    assert "зовут" in text.lower() or "имя" in text.lower()


@pytest.mark.asyncio
async def test_name_valid_moves_to_phone(session: AsyncSession) -> None:
    from src.handlers.client.booking import handle_name

    msg = _FakeMsg(from_user=_FakeUser(id=88))
    msg.text = "Анна"
    state = _make_fsm(88)
    await state.set_state(ClientBooking.EnteringName)

    await handle_name(msg, state=state)

    assert await state.get_state() == ClientBooking.EnteringPhone.state
    data = await state.get_data()
    assert data["name"] == "Анна"


@pytest.mark.asyncio
async def test_name_empty_retries_same_state(session: AsyncSession) -> None:
    from src.handlers.client.booking import handle_name

    msg = _FakeMsg(from_user=_FakeUser(id=89))
    msg.text = "   "
    state = _make_fsm(89)
    await state.set_state(ClientBooking.EnteringName)

    await handle_name(msg, state=state)

    assert await state.get_state() == ClientBooking.EnteringName.state
    assert msg.answers  # retry prompt shown


@pytest.mark.asyncio
async def test_phone_invalid_retries(session: AsyncSession) -> None:
    from src.handlers.client.booking import handle_phone

    msg = _FakeMsg(from_user=_FakeUser(id=90))
    msg.text = "abc"
    state = _make_fsm(90)
    await state.set_state(ClientBooking.EnteringPhone)

    await handle_phone(msg, state=state, session=session)

    assert await state.get_state() == ClientBooking.EnteringPhone.state


@pytest.mark.asyncio
async def test_phone_valid_renders_confirm(session: AsyncSession) -> None:
    from src.handlers.client.booking import handle_phone
    master = Master(
        tg_id=9200, name="М",
        work_hours={"mon": [["10:00", "19:00"]]}, breaks={},
        slot_step_min=60, timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=91))
    msg.text = "+374 99 111 222"
    state = _make_fsm(91)
    await state.set_state(ClientBooking.EnteringPhone)
    await state.update_data(
        master_id=str(master.id),
        service_id=str(service.id),
        date="2026-05-04",
        start_at=datetime(2026, 5, 4, 10, 0, tzinfo=UTC).isoformat(),
        name="Аня",
    )

    await handle_phone(msg, state=state, session=session)

    assert await state.get_state() == ClientBooking.Confirming.state
    data = await state.get_data()
    assert data["phone"] == "+37499111222"
    assert msg.answers
    text, kb = msg.answers[-1]
    assert "Подтвердить" in text or "проверьте" in text.lower()
    assert kb is not None


@pytest.mark.asyncio
async def test_confirm_creates_pending_and_notifies_master(
    session: AsyncSession,
) -> None:
    from src.handlers.client.booking import handle_confirm
    master = Master(
        tg_id=9300, name="М",
        work_hours={"mon": [["10:00", "19:00"]]}, breaks={},
        slot_step_min=60, timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=92))
    cb = _FakeCallback(data="client_confirm", from_user=_FakeUser(id=92), message=msg)
    state = _make_fsm(92)
    await state.set_state(ClientBooking.Confirming)
    start_at = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    await state.update_data(
        master_id=str(master.id),
        service_id=str(service.id),
        date="2026-05-04",
        start_at=start_at.isoformat(),
        name="Аня",
        phone="+37499111222",
    )

    bot = AsyncMock()
    await handle_confirm(cb, state=state, session=session, bot=bot)

    # FSM cleared:
    assert await state.get_state() is None
    # Master was notified:
    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == master.tg_id
    # Client got confirmation:
    text, _ = msg.answers[-1]
    assert "отправлена" in text.lower() or "ждите" in text.lower()


@pytest.mark.asyncio
async def test_confirm_handles_slot_taken(session: AsyncSession) -> None:
    from src.handlers.client.booking import handle_confirm
    from src.repositories.appointments import AppointmentRepository

    master = Master(
        tg_id=9400, name="М",
        work_hours={"mon": [["10:00", "19:00"]]}, breaks={},
        slot_step_min=60, timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    existing_client = Client(master_id=master.id, name="Занимающий", phone="+37499000000")
    session.add(existing_client)
    await session.flush()
    # Pre-book the same slot so create_pending will hit the unique index.
    repo = AppointmentRepository(session)
    start_at = datetime(2026, 5, 4, 6, 0, tzinfo=UTC)  # 10:00 Yerevan
    await repo.create(
        master_id=master.id, client_id=existing_client.id, service_id=service.id,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=60),
        status="confirmed", source="client_request",
    )
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=93))
    cb = _FakeCallback(data="client_confirm", from_user=_FakeUser(id=93), message=msg)
    state = _make_fsm(93)
    await state.set_state(ClientBooking.Confirming)
    await state.update_data(
        master_id=str(master.id),
        service_id=str(service.id),
        date="2026-05-04",
        start_at=start_at.isoformat(),
        name="Аня",
        phone="+37499111222",
    )

    bot = AsyncMock()
    await handle_confirm(cb, state=state, session=session, bot=bot)

    # FSM returned to ChoosingTime so client can pick again.
    assert await state.get_state() == ClientBooking.ChoosingTime.state
    # Master NOT notified:
    bot.send_message.assert_not_awaited()
    # Client got the taken message + slots grid:
    texts = [t for t, _ in msg.answers]
    assert any("заняли" in t.lower() for t in texts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_client_booking.py -v`
Expected: FAIL (handle_time_pick / handle_name / handle_phone / handle_confirm missing).

- [ ] **Step 3: Extend `src/handlers/client/booking.py`**

Add these imports at the top (in addition to existing):

```python
from aiogram import F
from aiogram.types import Message
from aiogram.types.bot import Bot  # Bot type for dispatcher DI

from src.callback_data.slots import SlotCallback
from src.exceptions import SlotAlreadyTaken
from src.keyboards.slots import approval_kb, confirm_kb
from src.repositories.clients import ClientRepository
from src.strings import strings
from src.utils.phone import normalize as normalize_phone
```

(Collapse duplicates — `strings` and `now_utc` are already imported.)

Append these handlers to the module:

```python
@router.callback_query(SlotCallback.filter(), ClientBooking.ChoosingTime)
async def handle_time_pick(
    callback: CallbackQuery,
    callback_data: SlotCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    master_id = UUID(data["master_id"])
    service_id = UUID(data["service_id"])
    picked_day = date.fromisoformat(data["date"])

    master, service = await _load_master_service(session, master_id, service_id)
    if master is None or service is None:
        await callback.answer(strings.CLIENT_NO_SERVICES, show_alert=True)
        await state.clear()
        return

    tz = ZoneInfo(master.timezone)
    local_start = datetime(
        picked_day.year, picked_day.month, picked_day.day,
        callback_data.hour, callback_data.minute, tzinfo=tz,
    )
    start_at_utc = local_start.astimezone(ZoneInfo("UTC"))

    await state.update_data(start_at=start_at_utc.isoformat())
    await state.set_state(ClientBooking.EnteringName)
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.CLIENT_ASK_NAME)


@router.message(ClientBooking.EnteringName)
async def handle_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not (1 <= len(name) <= 60):
        await message.answer(strings.CLIENT_BAD_NAME)
        return
    await state.update_data(name=name)
    await state.set_state(ClientBooking.EnteringPhone)
    await message.answer(strings.CLIENT_ASK_PHONE)


@router.message(ClientBooking.EnteringPhone)
async def handle_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()
    normalized = normalize_phone(raw)
    if normalized is None:
        await message.answer(strings.CLIENT_BAD_PHONE)
        return

    await state.update_data(phone=normalized)
    await state.set_state(ClientBooking.Confirming)

    data = await state.get_data()
    master_id = UUID(data["master_id"])
    service_id = UUID(data["service_id"])
    master, service = await _load_master_service(session, master_id, service_id)
    if master is None or service is None:
        await state.clear()
        await message.answer(strings.CLIENT_NO_SERVICES)
        return

    tz = ZoneInfo(master.timezone)
    start_at_utc = datetime.fromisoformat(data["start_at"])
    local = start_at_utc.astimezone(tz)
    summary = strings.CLIENT_CONFIRM_TITLE.format(
        service=service.name,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        name=data["name"],
        phone=normalized,
    )
    await message.answer(summary, reply_markup=confirm_kb())


@router.callback_query(F.data == "client_cancel")
async def handle_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.CLIENT_CANCELLED)


@router.callback_query(F.data == "client_back", ClientBooking.ChoosingTime)
async def handle_back_from_time(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    master_id = UUID(data["master_id"])
    service_id = UUID(data["service_id"])
    master, service = await _load_master_service(session, master_id, service_id)
    if master is None or service is None:
        await state.clear()
        await callback.answer()
        return
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await _render_calendar(
            target=callback.message, master=master, service=service,
            state=state, session=session,
        )


@router.callback_query(F.data == "client_confirm", ClientBooking.Confirming)
async def handle_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    data = await state.get_data()
    master_id = UUID(data["master_id"])
    service_id = UUID(data["service_id"])
    master, service = await _load_master_service(session, master_id, service_id)
    if master is None or service is None:
        await state.clear()
        await callback.answer(strings.CLIENT_NO_SERVICES, show_alert=True)
        return

    c_repo = ClientRepository(session)
    tg_id = callback.from_user.id if callback.from_user else None
    client_row = await c_repo.upsert_by_phone(
        master_id=master.id,
        phone=data["phone"],
        name=data["name"],
        tg_id=tg_id,
    )
    await session.commit()  # persist client before pending appointment

    start_at_utc = datetime.fromisoformat(data["start_at"])
    svc = BookingService(session)
    try:
        appt = await svc.create_pending(
            master=master, client=client_row, service=service, start_at=start_at_utc,
        )
    except SlotAlreadyTaken:
        await callback.answer(strings.CLIENT_SLOT_TAKEN, show_alert=True)
        await state.set_state(ClientBooking.ChoosingTime)
        tz = ZoneInfo(master.timezone)
        slots = await svc.get_free_slots(
            master, service, start_at_utc.astimezone(tz).date(), now=now_utc(),
        )
        if callback.message is not None and hasattr(callback.message, "answer"):
            if slots:
                await callback.message.answer(
                    strings.CLIENT_CHOOSE_TIME.format(
                        date=start_at_utc.astimezone(tz).strftime("%d.%m.%Y"),
                    ),
                    reply_markup=slots_grid(slots, tz=tz),
                )
            else:
                await callback.message.answer(strings.CLIENT_NO_SLOTS)
        return

    await state.clear()
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.CLIENT_SENT)

    # Notify master
    tz = ZoneInfo(master.timezone)
    local = appt.start_at.astimezone(tz)
    weekday_ru = strings.WEEKDAY_SHORT[local.weekday()]
    text = strings.APPT_NOTIFY_MASTER.format(
        name=client_row.name,
        phone=client_row.phone,
        service=service.name,
        duration=service.duration_min,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        weekday=weekday_ru,
    )
    await bot.send_message(
        chat_id=master.tg_id,
        text=text,
        reply_markup=approval_kb(appt.id),
    )
    log.info("pending_created", appointment_id=str(appt.id), master_tg=master.tg_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handlers_client_booking.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add src/handlers/client/booking.py tests/test_handlers_client_booking.py
git commit -m "feat(handlers): client time/name/phone/confirm + SlotAlreadyTaken recovery"
```

---

## Task 13: Master approval handlers — confirm / reject / history

**Files:**
- Create: `src/handlers/master/approve.py`
- Modify: `src/handlers/master/__init__.py`
- Test: `tests/test_handlers_master_approve.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_handlers_master_approve.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.approval import ApprovalCallback
from src.db.models import Client, Master, Service
from src.repositories.appointments import AppointmentRepository


@dataclass
class _User:
    id: int


@dataclass
class _Msg:
    from_user: _User | None
    text: str = ""
    edits: list[tuple[str, Any]] = field(default_factory=list)
    answers: list[tuple[str, Any]] = field(default_factory=list)

    async def edit_text(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.text = text
        self.edits.append((text, reply_markup))

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.answers.append((text, reply_markup))


@dataclass
class _Cb:
    from_user: _User
    message: _Msg
    data: str = ""
    answered: list[tuple[tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)

    async def answer(self, *args: Any, **kwargs: Any) -> None:
        self.answered.append((args, kwargs))


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=1111, name="М",
        work_hours={"mon": [["10:00", "19:00"]]}, breaks={},
        slot_step_min=60, timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Аня", phone="+37499000001", tg_id=2222)
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()
    return master, client, service


@pytest.mark.asyncio
async def test_confirm_happy_path_notifies_client(session: AsyncSession) -> None:
    from src.handlers.master.approve import cb_confirm

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="pending", source="client_request",
        decision_deadline=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
    )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id), text="🔔 Новая заявка…")
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="confirm", appointment_id=appt.id)

    await cb_confirm(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    await session.refresh(appt)
    assert appt.status == "confirmed"
    assert msg.edits  # original message edited with "Подтверждено"
    edited_text, edited_kb = msg.edits[-1]
    assert "Подтверждено" in edited_text
    assert edited_kb is None
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == client.tg_id


@pytest.mark.asyncio
async def test_confirm_already_processed_gives_alert(session: AsyncSession) -> None:
    from src.handlers.master.approve import cb_confirm

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="confirmed",  # already handled
        source="client_request",
        confirmed_at=datetime(2026, 5, 4, 6, 0, tzinfo=UTC),
    )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id))
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="confirm", appointment_id=appt.id)

    await cb_confirm(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    # Alert shown, no client notification sent.
    assert cb.answered
    _, kwargs = cb.answered[-1]
    assert kwargs.get("show_alert") is True
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_reject_updates_status_and_notifies_client(
    session: AsyncSession,
) -> None:
    from src.handlers.master.approve import cb_reject

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="pending", source="client_request",
        decision_deadline=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
    )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id), text="🔔 Новая заявка…")
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="reject", appointment_id=appt.id)

    await cb_reject(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    await session.refresh(appt)
    assert appt.status == "rejected"
    assert msg.edits
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == client.tg_id


@pytest.mark.asyncio
async def test_confirm_skips_client_notify_when_tg_id_missing(
    session: AsyncSession,
) -> None:
    from src.handlers.master.approve import cb_confirm

    master = Master(
        tg_id=1111, name="М",
        work_hours={"mon": [["10:00", "19:00"]]}, breaks={},
        slot_step_min=60, timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    # Client without tg_id (e.g., added manually by master).
    client = Client(master_id=master.id, name="Оффлайн", phone="+37499000099", tg_id=None)
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="pending", source="client_request",
        decision_deadline=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
    )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id))
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="confirm", appointment_id=appt.id)

    await cb_confirm(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    bot.send_message.assert_not_awaited()
    await session.refresh(appt)
    assert appt.status == "confirmed"


@pytest.mark.asyncio
async def test_history_empty_client(session: AsyncSession) -> None:
    from src.handlers.master.approve import cb_history

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="pending", source="client_request",
        decision_deadline=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
    )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id))
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="history", appointment_id=appt.id)

    await cb_history(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    # Alert text or message contains "нет истории".
    alert_texts = [args[0] for args, _ in cb.answered if args]
    msg_texts = [t for t, _ in msg.answers]
    all_texts = alert_texts + msg_texts
    assert any("истории" in t.lower() or "нет" in t.lower() for t in all_texts)


@pytest.mark.asyncio
async def test_history_with_long_history_uses_send_message(
    session: AsyncSession,
) -> None:
    from src.handlers.master.approve import cb_history

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    appt_pending = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="pending", source="client_request",
    )
    for i in range(8):
        await repo.create(
            master_id=master.id, client_id=client.id, service_id=service.id,
            start_at=datetime(2026, 1, 1 + i, 7, 0, tzinfo=UTC),
            end_at=datetime(2026, 1, 1 + i, 8, 0, tzinfo=UTC),
            status="confirmed", source="client_request",
        )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id))
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="history", appointment_id=appt_pending.id)

    await cb_history(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    # Long content goes via bot.send_message (alert has 200-char limit).
    bot.send_message.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_handlers_master_approve.py -v`
Expected: FAIL (ModuleNotFoundError: src.handlers.master.approve).

- [ ] **Step 3: Implement `src/handlers/master/approve.py`**

```python
from __future__ import annotations

from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.approval import ApprovalCallback
from src.db.models import Master
from src.exceptions import InvalidState, NotFound
from src.repositories.appointments import AppointmentRepository
from src.repositories.clients import ClientRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.strings import strings
from src.utils.time import now_utc

router = Router(name="master_approve")
log: structlog.stdlib.BoundLogger = structlog.get_logger()

_ALERT_LIMIT = 190  # Telegram limit is 200; leave headroom for UTF-16 surrogates.
_STATUS_LABELS = {
    "confirmed": "APPT_STATUS_CONFIRMED",
    "cancelled": "APPT_STATUS_CANCELLED",
    "rejected": "APPT_STATUS_REJECTED",
    "completed": "APPT_STATUS_COMPLETED",
    "no_show": "APPT_STATUS_NO_SHOW",
}


async def _notify_client(bot: Bot, client_tg_id: int | None, text: str) -> None:
    if client_tg_id is None:
        return
    try:
        await bot.send_message(chat_id=client_tg_id, text=text)
    except Exception as exc:  # TelegramForbiddenError etc. — master already saw the update
        log.warning("client_notify_failed", tg_id=client_tg_id, error=repr(exc))


@router.callback_query(ApprovalCallback.filter())
async def route_approval(
    callback: CallbackQuery,
    callback_data: ApprovalCallback,
    master: Master | None,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if master is None:
        await callback.answer()
        return
    if callback_data.action == "confirm":
        await cb_confirm(callback, callback_data=callback_data, master=master, session=session, bot=bot)
    elif callback_data.action == "reject":
        await cb_reject(callback, callback_data=callback_data, master=master, session=session, bot=bot)
    elif callback_data.action == "history":
        await cb_history(callback, callback_data=callback_data, master=master, session=session, bot=bot)


async def cb_confirm(
    callback: CallbackQuery,
    *,
    callback_data: ApprovalCallback,
    master: Master,
    session: AsyncSession,
    bot: Bot,
) -> None:
    svc = BookingService(session)
    try:
        appt = await svc.confirm(callback_data.appointment_id, master_id=master.id)
    except NotFound:
        await callback.answer(strings.APPT_ALREADY_PROCESSED, show_alert=True)
        return
    except InvalidState:
        await callback.answer(strings.APPT_ALREADY_PROCESSED, show_alert=True)
        return

    tz = ZoneInfo(master.timezone)
    local_now = now_utc().astimezone(tz)
    stamp = strings.APPT_CONFIRMED_STAMP.format(time=local_now.strftime("%H:%M"))

    if callback.message is not None and hasattr(callback.message, "edit_text"):
        original = getattr(callback.message, "text", "") or ""
        await callback.message.edit_text(original + stamp, reply_markup=None)
    await callback.answer()

    # Notify client
    c_repo = ClientRepository(session)
    client = await c_repo.get(appt.client_id)
    if client is None:
        return
    s_repo = ServiceRepository(session)
    service = await s_repo.get(appt.service_id, master_id=master.id)
    if service is None:
        return
    local_appt = appt.start_at.astimezone(tz)
    text = strings.CLIENT_APPT_CONFIRMED.format(
        date=local_appt.strftime("%d.%m.%Y"),
        time=local_appt.strftime("%H:%M"),
    )
    await _notify_client(bot, client.tg_id, text)
    log.info("appointment_confirmed", id=str(appt.id))


async def cb_reject(
    callback: CallbackQuery,
    *,
    callback_data: ApprovalCallback,
    master: Master,
    session: AsyncSession,
    bot: Bot,
) -> None:
    svc = BookingService(session)
    try:
        appt = await svc.reject(callback_data.appointment_id, master_id=master.id)
    except NotFound:
        await callback.answer(strings.APPT_ALREADY_PROCESSED, show_alert=True)
        return
    except InvalidState:
        await callback.answer(strings.APPT_ALREADY_PROCESSED, show_alert=True)
        return

    tz = ZoneInfo(master.timezone)
    local_now = now_utc().astimezone(tz)
    stamp = strings.APPT_REJECTED_STAMP.format(time=local_now.strftime("%H:%M"))

    if callback.message is not None and hasattr(callback.message, "edit_text"):
        original = getattr(callback.message, "text", "") or ""
        await callback.message.edit_text(original + stamp, reply_markup=None)
    await callback.answer()

    c_repo = ClientRepository(session)
    client = await c_repo.get(appt.client_id)
    if client is None:
        return
    local_appt = appt.start_at.astimezone(tz)
    text = strings.CLIENT_APPT_REJECTED.format(
        date=local_appt.strftime("%d.%m.%Y"),
        time=local_appt.strftime("%H:%M"),
    )
    await _notify_client(bot, client.tg_id, text)
    log.info("appointment_rejected", id=str(appt.id))


async def cb_history(
    callback: CallbackQuery,
    *,
    callback_data: ApprovalCallback,
    master: Master,
    session: AsyncSession,
    bot: Bot,
) -> None:
    a_repo = AppointmentRepository(session)
    appt = await a_repo.get(callback_data.appointment_id, master_id=master.id)
    if appt is None:
        await callback.answer(strings.APPT_ALREADY_PROCESSED, show_alert=True)
        return

    c_repo = ClientRepository(session)
    client = await c_repo.get(appt.client_id)
    if client is None:
        await callback.answer(strings.APPT_HISTORY_EMPTY, show_alert=True)
        return

    svc = BookingService(session)
    history = await svc.list_client_history(master, client.id, limit=10)
    if not history:
        await callback.answer(strings.APPT_HISTORY_EMPTY, show_alert=True)
        return

    tz = ZoneInfo(master.timezone)
    s_repo = ServiceRepository(session)
    lines = [strings.APPT_HISTORY_TITLE.format(name=client.name, limit=len(history))]
    for h in history:
        local = h.start_at.astimezone(tz)
        svc_row = await s_repo.get(h.service_id, master_id=master.id)
        svc_name = svc_row.name if svc_row else "—"
        status_key = _STATUS_LABELS.get(h.status, "APPT_STATUS_CONFIRMED")
        status_label = getattr(strings, status_key)
        lines.append(
            strings.APPT_HISTORY_LINE.format(
                date=local.strftime("%d.%m.%Y"),
                time=local.strftime("%H:%M"),
                service=svc_name,
                status=status_label,
            )
        )
    text = "\n".join(lines)

    if len(text) <= _ALERT_LIMIT:
        await callback.answer(text, show_alert=True)
        return

    await callback.answer()
    await bot.send_message(chat_id=master.tg_id, text=text)
```

- [ ] **Step 4: Wire the router in `src/handlers/master/__init__.py`**

```python
from __future__ import annotations

from aiogram import Router

from src.handlers.master.approve import router as approve_router
from src.handlers.master.menu import router as menu_router
from src.handlers.master.services import router as services_router
from src.handlers.master.settings import router as settings_router
from src.handlers.master.start import router as start_router

router = Router(name="master")
router.include_router(start_router)
router.include_router(menu_router)
router.include_router(services_router)
router.include_router(settings_router)
router.include_router(approve_router)

__all__ = ["router"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_handlers_master_approve.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/handlers/master/approve.py src/handlers/master/__init__.py \
        tests/test_handlers_master_approve.py
git commit -m "feat(handlers): master approval — confirm/reject/history callbacks"
```

---

## Task 14: Wire client router + verify end-to-end

**Files:**
- Modify: `src/handlers/__init__.py`
- Modify: `src/handlers/master/start.py`

- [ ] **Step 1: Include the client router**

Replace `src/handlers/__init__.py` contents with:

```python
from __future__ import annotations

from aiogram import Router

from src.handlers.client import router as client_router
from src.handlers.master import router as master_router


def build_root_router() -> Router:
    root = Router(name="root")
    # Master router runs first so master's own /start matches its handler
    # (UserMiddleware populates `master` → handler returns early for non-matching clients).
    root.include_router(master_router)
    root.include_router(client_router)
    return root


__all__ = ["build_root_router"]
```

- [ ] **Step 2: Remove dead client branch from `src/handlers/master/start.py`**

Edit `handle_start`: remove the `if client is not None: ... CLIENT_STUB` block (the client flow is now owned by the client router). The final fallthrough `START_UNKNOWN` also goes (client router handles unknown users).

Replace the body of `handle_start` with:

```python
async def handle_start(
    message: Message,
    master: Master | None,
    client: Client | None,
    state: FSMContext,
) -> None:
    del client  # handled by client router
    tg_id = message.from_user.id if message.from_user else None
    log.info(
        "start_received",
        tg_id=tg_id,
        has_master=master is not None,
    )

    if master is not None:
        await state.clear()
        await message.answer(strings.START_WELCOME_BACK, reply_markup=main_menu())
        return

    if tg_id is not None and tg_id in settings.admin_tg_ids:
        await state.set_state(MasterRegister.waiting_lang)
        await message.answer(strings.LANG_PICK_PROMPT, reply_markup=lang_picker())
        return

    # Fall through — the client router picks this up because master router
    # did not call message.answer for non-admin, non-master users.
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest -q --cov=src --cov-report=term-missing`
Expected: All tests pass; `src/services/availability.py` 100%; `src/services/booking.py` ≥95%; `src/utils/phone.py` 100%; `src/repositories/clients.py` ≥90%; new handler files ≥60%.

- [ ] **Step 4: Run linters**

Run in order:
- `ruff check .` — Expected: clean.
- `ruff format --check .` — Expected: clean (or run `ruff format .` to fix).
- `mypy src/` — Expected: clean.

If any step fails, fix inline (no `# type: ignore` without a comment explaining why).

- [ ] **Step 5: Commit**

```bash
git add src/handlers/__init__.py src/handlers/master/start.py
git commit -m "feat(router): wire client router; master start no longer owns client path"
```

- [ ] **Step 6: Tag epic complete**

Once every test still passes after linters, tag the epic locally:

```bash
git tag v0.4.0-epic-4
git log --oneline v0.3.0-epic-3..HEAD
```

Do NOT push yet — `main` is protected, wait for user's explicit authorization.

---

## Coverage gate (run before declaring done)

```bash
pytest -q --cov=src --cov-report=term-missing \
  --cov-fail-under=85 \
  --cov-branch
```

Per-file expectations (ratchet, not gate):

| File                               | Target |
|------------------------------------|--------|
| `src/services/availability.py`     | 100%   |
| `src/services/booking.py`          | ≥95%   |
| `src/repositories/clients.py`      | ≥90%   |
| `src/repositories/masters.py`      | ≥90%   |
| `src/repositories/appointments.py` | ≥90%   |
| `src/utils/phone.py`               | 100%   |
| `src/keyboards/calendar.py`        | ≥90%   |
| `src/keyboards/slots.py`           | ≥90%   |
| `src/handlers/client/*.py`         | ≥60%   |
| `src/handlers/master/approve.py`   | ≥60%   |

---

## Self-review

**Spec coverage (mapping to tasks):**

- §1 Scope & file structure → reflected in file-structure section of this plan (Tasks 1–14 cover every file).
- §2 Calendar with day-load coloring → Task 5 (pure `calculate_day_loads`) + Task 9 (`keyboards/calendar.py`).
- §2 CalendarCallback typed → Task 7.
- §2 DayLoad literal 🟢🟡🔴⚫ rules → Task 9 `_classify` + emoji map tests.
- §2 Nav window [today_month, +MAX_MONTHS_AHEAD] → Task 9 `_months_between` / `MAX_MONTHS_AHEAD` tests.
- §3 `ClientBooking` FSM states → Task 8.
- §3 `/start` → `get_singleton` resolves master → Task 11.
- §3 Service pick → Task 11, date pick → Task 11, time pick / name / phone / confirm → Task 12.
- §3 Phone validation (`utils.phone.normalize`) → Task 1.
- §3 `ClientRepository.upsert_by_phone` → Task 3; used in `handle_confirm` (Task 12).
- §3 SlotAlreadyTaken on confirm → return to `ChoosingTime` with fresh grid → Task 12 test.
- §3 `/cancel` command + cancel button → Task 11 + Task 12.
- §3 Minimal state.data (IDs only) → Task 11/12 (only UUIDs + isoformat strings stored).
- §4 Master notification template → Task 12 `handle_confirm` (send_message at end).
- §4 `ApprovalCallback` → Task 7; typed buttons via `approval_kb` → Task 10.
- §4 Confirm/Reject handlers editing original message with stamp → Task 13.
- §4 InvalidState / NotFound → already-processed alert → Task 13 tests.
- §4 History via alert or `send_message` fallback → Task 13 `cb_history`.
- §4 Client without tg_id: skip send_message, no error → Task 13 test.
- §4 `list_client_history` service + `list_for_client` repo → Tasks 4 + 6.
- §4 Scoping by master_id — delegated to existing `BookingService.confirm/reject` (Epic 3) and `repo.list_for_client` (Task 4).
- §5 Testing strategy — each section has its tests in-plan; coverage gate at the end.

**Placeholder scan:** No "TBD" / "implement later" / "similar to Task N" / bare "add error handling" — every code step has complete source.

**Type consistency:**
- `DayLoad = Literal["off", "full", "tight", "free"]` — used only in `keyboards/calendar.py`; `calculate_day_loads` returns `dict[date, int]` and `_classify` is the sole boundary translating `int → DayLoad`. Tasks 5, 9, 10 agree on the int contract.
- `CalendarCallback.day: int = 0` default used for `nav`/`noop` — tests in Task 7 and usage in Task 9 agree.
- `MasterRepository.get_singleton()` introduced in Task 2 and called in Tasks 11 & 13 (via `_load_master_service`). Signatures match.
- `ClientRepository.get(client_id)` (Task 3) and `.upsert_by_phone(master_id=, phone=, name=, tg_id=)` (Task 3) — signatures match their call sites in Tasks 12 & 13.
- `AppointmentRepository.list_for_client(master_id, client_id, *, limit=10, exclude_statuses=("pending",))` (Task 4) — matches usage in `BookingService.list_client_history(master, client_id, limit=10)` (Task 6).
- Handler tests import from fully-qualified module paths that match the create paths in the Files sections of each task.

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-21-epic-4-client-booking.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
