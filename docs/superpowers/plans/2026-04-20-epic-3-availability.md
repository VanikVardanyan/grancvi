# Epic 3 — Availability & Booking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Calculate free time slots for a given master+service+day, and manage the appointment lifecycle (pending → confirmed/rejected/cancelled, plus master-manual bookings), with DB-level protection against double-booking.

**Architecture:** Pure `calculate_free_slots` function (no DB, no wall-clock — `now` injected) called by `BookingService.get_free_slots`. Appointment writes go through `BookingService`, which owns its own commit/rollback on the create paths so that the `uq_appointment_slot` partial unique index can arbitrate concurrent inserts via `IntegrityError → SlotAlreadyTaken`. Everything else (confirm/reject/cancel) mutates in-place and lets the DB middleware commit on handler return.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 async, asyncpg, PostgreSQL 16 partial unique index, zoneinfo.

**Preconditions:**
- Epics 1–2 merged. Tag `v0.2.0-epic-2` is the base.
- `Appointment` model + `uq_appointment_slot` partial unique index exist (see `src/db/models.py:122-176`).
- `tests/conftest.py` provides `session` and `session_maker` fixtures against a real Postgres.

---

## File Structure

**Create:**
- `src/utils/time.py` — `now_utc()`, `to_utc()`, `to_yerevan()`, `YEREVAN` constant. Referenced by CLAUDE.md but not yet created. Keeps wall-clock access in one place.
- `src/exceptions.py` — `SlotAlreadyTaken`, `NotFound`, `InvalidState`. Domain exceptions, no stack trace embellishment.
- `src/services/__init__.py` — empty namespace marker.
- `src/services/availability.py` — pure `calculate_free_slots`. No DB. No `datetime.now()`. Everything is an argument.
- `src/services/booking.py` — `BookingService` use-cases. Owns commit/rollback on `create_pending` and `create_manual`; read-modify on `confirm`/`reject`/`cancel` relies on the DB middleware to commit.
- `src/repositories/appointments.py` — `AppointmentRepository` thin CRUD + `list_active_for_day` + `get_pending_past_deadline`.
- `tests/test_utils_time.py` — unit tests for the new helpers.
- `tests/test_availability.py` — full table of scenarios against the pure function.
- `tests/test_repositories_appointments.py` — DB-backed repo tests.
- `tests/test_services_booking.py` — DB-backed service tests + the race-condition test using `session_maker`.

**Modify:**
- Nothing in existing modules. All additions are new files.

**Responsibilities:**
- Availability math lives in `availability.py` and is pure — so we can hit 100% coverage via table-driven unit tests.
- Any wall-clock access (`now`) is injected into service/ util functions; tests never monkey-patch `datetime.now`.
- Repository returns SQLAlchemy model instances. The service translates domain errors (`SlotAlreadyTaken`, `NotFound`, `InvalidState`). Handlers will catch those in Epic 4+.

---

## Task 1: Time utilities

**Files:**
- Create: `src/utils/time.py`
- Create: `tests/test_utils_time.py`

- [ ] **Step 1: Write failing test `tests/test_utils_time.py`**

```python
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from src.utils.time import YEREVAN, now_utc, to_utc, to_yerevan


def test_yerevan_constant_is_asia_yerevan() -> None:
    assert YEREVAN == ZoneInfo("Asia/Yerevan")


def test_now_utc_is_tz_aware_and_utc() -> None:
    got = now_utc()
    assert got.tzinfo is not None
    assert got.utcoffset() == datetime(2026, 1, 1, tzinfo=UTC).utcoffset()


def test_to_utc_converts_from_local_tz() -> None:
    local = datetime(2026, 4, 20, 14, 0, tzinfo=YEREVAN)
    assert to_utc(local) == datetime(2026, 4, 20, 10, 0, tzinfo=UTC)


def test_to_yerevan_converts_from_utc() -> None:
    utc = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)
    assert to_yerevan(utc) == datetime(2026, 4, 20, 14, 0, tzinfo=YEREVAN)


def test_to_utc_rejects_naive() -> None:
    with pytest.raises(ValueError):
        to_utc(datetime(2026, 4, 20, 14, 0))


def test_to_yerevan_rejects_naive() -> None:
    with pytest.raises(ValueError):
        to_yerevan(datetime(2026, 4, 20, 14, 0))
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `uv run pytest tests/test_utils_time.py -v`
Expected: `ModuleNotFoundError: No module named 'src.utils.time'` (or AttributeError on `YEREVAN`).

- [ ] **Step 3: Implement `src/utils/time.py`**

```python
from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

YEREVAN = ZoneInfo("Asia/Yerevan")


def now_utc() -> datetime:
    """Tz-aware 'now' in UTC. Keeps wall-clock access in one place."""
    return datetime.now(UTC)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed")
    return dt.astimezone(UTC)


def to_yerevan(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed")
    return dt.astimezone(YEREVAN)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `uv run pytest tests/test_utils_time.py -v`
Expected: 6 passed.

- [ ] **Step 5: Linters**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/utils/time.py tests/test_utils_time.py
git commit -m "feat(utils): tz-aware time helpers (now_utc / to_utc / to_yerevan)"
```

---

## Task 2: Domain exceptions

**Files:**
- Create: `src/exceptions.py`
- Test coverage is incidental — these classes are exercised by later tasks.

- [ ] **Step 1: Create `src/exceptions.py`**

```python
from __future__ import annotations


class SlotAlreadyTaken(Exception):
    """Raised when the unique partial index rejects a pending/confirmed insert.

    Handlers should respond by re-rendering the current grid of free slots.
    """


class NotFound(Exception):
    """Raised by services when a referenced appointment does not exist."""


class InvalidState(Exception):
    """Raised when an appointment transition is not allowed from its current status.

    Example: trying to confirm an appointment that is already cancelled.
    """
```

- [ ] **Step 2: Verify import round-trip**

Run: `uv run python -c "from src.exceptions import SlotAlreadyTaken, NotFound, InvalidState; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Linters**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/`
Expected: all clean.

- [ ] **Step 4: Commit**

```bash
git add src/exceptions.py
git commit -m "feat(exceptions): domain errors SlotAlreadyTaken / NotFound / InvalidState"
```

---

## Task 3: `calculate_free_slots` pure function

Full TDD: write all scenario tests first, verify they fail, implement the function, verify they pass.

**Files:**
- Create: `src/services/__init__.py`
- Create: `src/services/availability.py`
- Create: `tests/test_availability.py`

- [ ] **Step 1: Create `src/services/__init__.py`**

```python
from __future__ import annotations
```

- [ ] **Step 2: Write failing test file `tests/test_availability.py`**

```python
from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from src.services.availability import calculate_free_slots

YEREVAN = ZoneInfo("Asia/Yerevan")

# Monday 2026-04-20 is the anchor date for most tests.
MON = date(2026, 4, 20)

WORK_MON_10_19: dict[str, list[list[str]]] = {"mon": [["10:00", "19:00"]]}
NO_BREAKS: dict[str, list[list[str]]] = {}


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _yer(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=YEREVAN)


def test_day_off_returns_empty() -> None:
    # No entry for "mon" in work_hours at all → day off.
    result = calculate_free_slots(
        work_hours={},
        breaks=NO_BREAKS,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=20,
        service_duration_min=30,
    )
    assert result == []


def test_empty_day_full_grid() -> None:
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    # 10, 11, 12, 13, 14, 15, 16, 17, 18 (18+60 == 19 fits)
    assert [s.hour for s in result] == [10, 11, 12, 13, 14, 15, 16, 17, 18]
    assert result[0] == _yer(2026, 4, 20, 10)
    assert result[-1] == _yer(2026, 4, 20, 18)


def test_booking_in_middle_splits_window() -> None:
    # 13:00-14:00 Yerevan = 09:00-10:00 UTC
    booked = [(_utc(2026, 4, 20, 9), _utc(2026, 4, 20, 10))]
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=booked,
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert [s.hour for s in result] == [10, 11, 12, 14, 15, 16, 17, 18]


def test_break_lunch_splits_window() -> None:
    breaks = {"mon": [["13:00", "14:00"]]}
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=breaks,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert [s.hour for s in result] == [10, 11, 12, 14, 15, 16, 17, 18]


def test_today_past_slots_filtered() -> None:
    # "now" is 14:30 Yerevan on the same day — slots at 14:00 and earlier are dropped.
    now = _yer(2026, 4, 20, 14, 30)
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=now,
    )
    assert [s.hour for s in result] == [15, 16, 17, 18]


def test_past_filter_not_applied_to_future_day() -> None:
    # "now" is on Mon, but we're querying Tue — past filter must be skipped.
    now = _yer(2026, 4, 20, 14, 30)
    tue = date(2026, 4, 21)
    result = calculate_free_slots(
        work_hours={"tue": [["10:00", "19:00"]]},
        breaks=NO_BREAKS,
        booked=[],
        day=tue,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=now,
    )
    assert len(result) == 9


def test_service_too_long_returns_empty() -> None:
    result = calculate_free_slots(
        work_hours={"mon": [["10:00", "11:00"]]},
        breaks=NO_BREAKS,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=20,
        service_duration_min=120,
    )
    assert result == []


def test_booking_at_window_start_removes_first_slot() -> None:
    # 10:00-11:00 Yerevan = 06:00-07:00 UTC
    booked = [(_utc(2026, 4, 20, 6), _utc(2026, 4, 20, 7))]
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=booked,
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert [s.hour for s in result] == [11, 12, 13, 14, 15, 16, 17, 18]


def test_booking_at_window_end_removes_last_slot() -> None:
    # 18:00-19:00 Yerevan = 14:00-15:00 UTC
    booked = [(_utc(2026, 4, 20, 14), _utc(2026, 4, 20, 15))]
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=booked,
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert [s.hour for s in result] == [10, 11, 12, 13, 14, 15, 16, 17]


def test_split_day_morning_and_evening() -> None:
    # Two intervals: 10-13 and 15-19. 13-15 is neither work nor break — just a gap.
    wh = {"mon": [["10:00", "13:00"], ["15:00", "19:00"]]}
    result = calculate_free_slots(
        work_hours=wh,
        breaks=NO_BREAKS,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert [s.hour for s in result] == [10, 11, 12, 15, 16, 17, 18]


def test_booking_entirely_outside_work_window_ignored() -> None:
    # 08:00-09:00 Yerevan — before the 10:00 work start. Must not crash or clip anything.
    booked = [(_utc(2026, 4, 20, 4), _utc(2026, 4, 20, 5))]
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=booked,
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert len(result) == 9


def test_zero_duration_booking_does_not_remove_slots() -> None:
    # A booked tuple with start == end — defensive: shouldn't blow up.
    booked = [(_utc(2026, 4, 20, 9), _utc(2026, 4, 20, 9))]
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=booked,
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert len(result) == 9
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `uv run pytest tests/test_availability.py -v`
Expected: `ModuleNotFoundError: No module named 'src.services.availability'`.

- [ ] **Step 4: Implement `src/services/availability.py`**

```python
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _parse_intervals(raw: list[list[str]]) -> list[tuple[int, int]]:
    """[['10:00','19:00'], ...] → [(600, 1140), ...] (minutes from midnight)."""
    out: list[tuple[int, int]] = []
    for start_s, end_s in raw:
        sh, sm = start_s.split(":")
        eh, em = end_s.split(":")
        out.append((int(sh) * 60 + int(sm), int(eh) * 60 + int(em)))
    return out


def _subtract(
    windows: list[tuple[int, int]], cuts: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Remove each `cut` interval from every window, returning surviving fragments."""
    result = list(windows)
    for c_start, c_end in cuts:
        if c_end <= c_start:
            # zero / negative duration — leave windows alone
            continue
        next_result: list[tuple[int, int]] = []
        for w_start, w_end in result:
            # No overlap
            if c_end <= w_start or c_start >= w_end:
                next_result.append((w_start, w_end))
                continue
            # Left fragment
            if c_start > w_start:
                next_result.append((w_start, c_start))
            # Right fragment
            if c_end < w_end:
                next_result.append((c_end, w_end))
        result = next_result
    return result


def calculate_free_slots(
    work_hours: dict[str, list[list[str]]],
    breaks: dict[str, list[list[str]]],
    booked: list[tuple[datetime, datetime]],
    day: date,
    tz: ZoneInfo,
    slot_step_min: int,
    service_duration_min: int,
    now: datetime | None = None,
) -> list[datetime]:
    """Return tz-aware start times (in `tz`) of every slot that fits the service.

    Pure function — no DB, no clock access. Caller must pass `now` if they want
    past slots filtered for today; otherwise the function never looks at wall time.
    """
    weekday = WEEKDAYS[day.weekday()]
    work_raw = work_hours.get(weekday)
    if not work_raw:
        return []

    work_windows = _parse_intervals(work_raw)
    break_windows = _parse_intervals(breaks.get(weekday, []))

    free_windows = _subtract(work_windows, break_windows)

    day_start_local = datetime(day.year, day.month, day.day, tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)

    booked_minutes: list[tuple[int, int]] = []
    for start_at, end_at in booked:
        start_local = start_at.astimezone(tz)
        end_local = end_at.astimezone(tz)
        # Ignore bookings entirely outside this day.
        if end_local <= day_start_local or start_local >= day_end_local:
            continue
        clipped_start = max(start_local, day_start_local)
        clipped_end = min(end_local, day_end_local)
        s_min = int((clipped_start - day_start_local).total_seconds() // 60)
        e_min = int((clipped_end - day_start_local).total_seconds() // 60)
        booked_minutes.append((s_min, e_min))

    free_windows = _subtract(free_windows, booked_minutes)

    slots: list[datetime] = []
    for w_start, w_end in free_windows:
        cursor = w_start
        while cursor + service_duration_min <= w_end:
            slots.append(day_start_local + timedelta(minutes=cursor))
            cursor += slot_step_min

    if now is not None:
        now_local = now.astimezone(tz)
        if now_local.date() == day:
            slots = [s for s in slots if s > now_local]

    return slots
```

- [ ] **Step 5: Run tests, verify all pass**

Run: `uv run pytest tests/test_availability.py -v`
Expected: 12 passed.

- [ ] **Step 6: Verify 100% coverage**

Run: `uv run pytest tests/test_availability.py --cov=src.services.availability --cov-report=term-missing`
Expected: `src/services/availability.py  ...  100%`. If any line shows up as missing, add a test that exercises it.

- [ ] **Step 7: Linters**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/`
Expected: all clean.

- [ ] **Step 8: Commit**

```bash
git add src/services/__init__.py src/services/availability.py tests/test_availability.py
git commit -m "feat(availability): pure calculate_free_slots with 100% coverage"
```

---

## Task 4: `AppointmentRepository`

**Files:**
- Create: `src/repositories/appointments.py`
- Create: `tests/test_repositories_appointments.py`

- [ ] **Step 1: Write failing test `tests/test_repositories_appointments.py`**

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master, Service
from src.repositories.appointments import AppointmentRepository


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(tg_id=1001, name="Анна")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Клиент", phone="+37490000001")
    session.add(client)
    service = Service(master_id=master.id, name="Чистка", duration_min=60)
    session.add(service)
    await session.flush()
    return master, client, service


@pytest.mark.asyncio
async def test_create_persists_row(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    start = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)

    appt = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status="pending",
        source="client_request",
    )
    await session.commit()

    assert appt.id is not None
    refreshed = await repo.get(appt.id)
    assert refreshed is not None
    assert refreshed.status == "pending"
    assert refreshed.start_at == start


@pytest.mark.asyncio
async def test_list_active_for_day_returns_only_overlapping(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)

    def at(hour: int) -> datetime:
        return datetime(2026, 4, 20, hour, 0, tzinfo=UTC)

    # On the day, pending — should appear
    a = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=at(6), end_at=at(7), status="pending", source="client_request",
    )
    # On the day, confirmed — should appear
    b = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=at(10), end_at=at(11), status="confirmed", source="client_request",
    )
    # On the day, cancelled — must NOT appear
    await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=at(12), end_at=at(13), status="cancelled", source="client_request",
    )
    # On previous day — must NOT appear
    await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 4, 19, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 19, 11, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    await session.commit()

    day_start = datetime(2026, 4, 20, 0, 0, tzinfo=UTC)
    day_end = datetime(2026, 4, 21, 0, 0, tzinfo=UTC)
    result = await repo.list_active_for_day(
        master.id, day_start_utc=day_start, day_end_utc=day_end
    )
    assert {r.id for r in result} == {a.id, b.id}


@pytest.mark.asyncio
async def test_get_scoped_by_master_returns_none_for_other_master(
    session: AsyncSession,
) -> None:
    master, client, service = await _seed(session)
    other = Master(tg_id=2002, name="Борис")
    session.add(other)
    await session.flush()

    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 20, 11, 0, tzinfo=UTC),
        status="pending", source="client_request",
    )
    await session.commit()

    assert await repo.get(appt.id, master_id=other.id) is None
    assert (await repo.get(appt.id, master_id=master.id)) is not None


@pytest.mark.asyncio
async def test_update_status_writes_through(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    start = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=start, end_at=start + timedelta(minutes=60),
        status="pending", source="client_request",
    )
    await session.commit()

    confirmed_at = datetime(2026, 4, 20, 9, 30, tzinfo=UTC)
    result = await repo.update_status(
        appt.id, master_id=master.id, status="confirmed", confirmed_at=confirmed_at
    )
    await session.commit()
    assert result is not None
    assert result.status == "confirmed"
    assert result.confirmed_at == confirmed_at


@pytest.mark.asyncio
async def test_update_status_other_master_returns_none(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    other = Master(tg_id=3003, name="Валерий")
    session.add(other)
    await session.flush()
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 20, 11, 0, tzinfo=UTC),
        status="pending", source="client_request",
    )
    await session.commit()

    result = await repo.update_status(
        appt.id, master_id=other.id, status="confirmed"
    )
    assert result is None
    # Still pending after the no-op
    refreshed = await repo.get(appt.id)
    assert refreshed is not None
    assert refreshed.status == "pending"


@pytest.mark.asyncio
async def test_get_pending_past_deadline_filters(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)

    def at(hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 4, 20, hour, minute, tzinfo=UTC)

    # Past deadline — should appear
    stale = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=at(15), end_at=at(16),
        status="pending", source="client_request",
        decision_deadline=at(10),
    )
    # Future deadline — must NOT appear
    await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=at(17), end_at=at(18),
        status="pending", source="client_request",
        decision_deadline=at(23),
    )
    # Not pending — must NOT appear
    await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=at(18), end_at=at(19),
        status="confirmed", source="client_request",
        decision_deadline=at(9),
    )
    await session.commit()

    now = at(12)
    result = await repo.get_pending_past_deadline(now=now)
    assert {r.id for r in result} == {stale.id}


@pytest.mark.asyncio
async def test_partial_unique_allows_cancelled_reinsert(session: AsyncSession) -> None:
    """The partial unique index only covers pending+confirmed — cancelled slots free up."""
    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    start = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)

    # First booking, then cancel it
    first = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=start, end_at=start + timedelta(minutes=60),
        status="pending", source="client_request",
    )
    await session.commit()

    await repo.update_status(first.id, master_id=master.id, status="cancelled")
    await session.commit()

    # Same slot, new booking — must succeed
    second = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=start, end_at=start + timedelta(minutes=60),
        status="pending", source="client_request",
    )
    await session.commit()
    assert second.id != first.id


@pytest.mark.asyncio
async def test_partial_unique_rejects_duplicate_pending(session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    start = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)

    await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=start, end_at=start + timedelta(minutes=60),
        status="pending", source="client_request",
    )
    await session.commit()

    with pytest.raises(IntegrityError):
        await repo.create(
            master_id=master.id, client_id=client.id, service_id=service.id,
            start_at=start, end_at=start + timedelta(minutes=60),
            status="pending", source="client_request",
        )
        await session.commit()
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_repositories_appointments.py -v`
Expected: `ModuleNotFoundError: No module named 'src.repositories.appointments'`.

- [ ] **Step 3: Implement `src/repositories/appointments.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment


class AppointmentRepository:
    """Appointment CRUD + day-scoped read for availability math."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active_for_day(
        self,
        master_id: UUID,
        *,
        day_start_utc: datetime,
        day_end_utc: datetime,
    ) -> list[Appointment]:
        """Appointments whose (start_at, end_at) overlaps [day_start, day_end) in UTC.

        Only `pending` and `confirmed` rows — cancelled/rejected/completed/no_show
        are excluded because they don't block the slot grid.
        """
        stmt = (
            select(Appointment)
            .where(
                Appointment.master_id == master_id,
                Appointment.status.in_(["pending", "confirmed"]),
                Appointment.start_at < day_end_utc,
                Appointment.end_at > day_start_utc,
            )
            .order_by(Appointment.start_at)
        )
        return list((await self._session.scalars(stmt)).all())

    async def get(
        self, appointment_id: UUID, *, master_id: UUID | None = None
    ) -> Appointment | None:
        stmt = select(Appointment).where(Appointment.id == appointment_id)
        if master_id is not None:
            stmt = stmt.where(Appointment.master_id == master_id)
        return cast(Appointment | None, await self._session.scalar(stmt))

    async def create(
        self,
        *,
        master_id: UUID,
        client_id: UUID,
        service_id: UUID,
        start_at: datetime,
        end_at: datetime,
        status: str,
        source: str,
        comment: str | None = None,
        decision_deadline: datetime | None = None,
        confirmed_at: datetime | None = None,
    ) -> Appointment:
        appt = Appointment(
            master_id=master_id,
            client_id=client_id,
            service_id=service_id,
            start_at=start_at,
            end_at=end_at,
            status=status,
            source=source,
            comment=comment,
            decision_deadline=decision_deadline,
            confirmed_at=confirmed_at,
        )
        self._session.add(appt)
        await self._session.flush()
        return appt

    async def update_status(
        self,
        appointment_id: UUID,
        *,
        status: str,
        master_id: UUID | None = None,
        confirmed_at: datetime | None = None,
        cancelled_at: datetime | None = None,
        cancelled_by: str | None = None,
    ) -> Appointment | None:
        appt = await self.get(appointment_id, master_id=master_id)
        if appt is None:
            return None
        appt.status = status
        if confirmed_at is not None:
            appt.confirmed_at = confirmed_at
        if cancelled_at is not None:
            appt.cancelled_at = cancelled_at
        if cancelled_by is not None:
            appt.cancelled_by = cancelled_by
        return appt

    async def get_pending_past_deadline(self, *, now: datetime) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(
                Appointment.status == "pending",
                Appointment.decision_deadline < now,
            )
            .order_by(Appointment.decision_deadline)
        )
        return list((await self._session.scalars(stmt)).all())
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_repositories_appointments.py -v`
Expected: 8 passed.

- [ ] **Step 5: Linters**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/repositories/appointments.py tests/test_repositories_appointments.py
git commit -m "feat(repo): AppointmentRepository with day-scoped list + unique-index sanity"
```

---

## Task 5: `BookingService.get_free_slots`

**Files:**
- Create: `src/services/booking.py` (first handler only — other methods in later tasks)
- Create: `tests/test_services_booking.py`

- [ ] **Step 1: Write failing test `tests/test_services_booking.py`**

```python
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master, Service
from src.services.booking import BookingService


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=9001,
        name="Мастер",
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        slot_step_min=60,
        timezone="Asia/Yerevan",
        decision_timeout_min=120,
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="К", phone="+37490000042")
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()
    return master, client, service


@pytest.mark.asyncio
async def test_get_free_slots_empty_day(session: AsyncSession) -> None:
    master, _, service = await _seed(session)
    await session.commit()

    svc = BookingService(session)
    result = await svc.get_free_slots(master, service, date(2026, 4, 20))
    assert [s.hour for s in result] == [10, 11, 12, 13, 14, 15, 16, 17, 18]


@pytest.mark.asyncio
async def test_get_free_slots_excludes_existing_booking(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    # Existing confirmed booking 13:00-14:00 Yerevan = 09:00-10:00 UTC
    from src.repositories.appointments import AppointmentRepository
    repo = AppointmentRepository(session)
    await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 4, 20, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 4, 20, 10, 0, tzinfo=UTC),
        status="confirmed", source="client_request",
    )
    await session.commit()

    svc = BookingService(session)
    result = await svc.get_free_slots(master, service, date(2026, 4, 20))
    assert [s.hour for s in result] == [10, 11, 12, 14, 15, 16, 17, 18]


@pytest.mark.asyncio
async def test_get_free_slots_respects_now_filter(session: AsyncSession) -> None:
    master, _, service = await _seed(session)
    await session.commit()

    # 14:30 Yerevan on the same day
    from zoneinfo import ZoneInfo
    now = datetime(2026, 4, 20, 14, 30, tzinfo=ZoneInfo("Asia/Yerevan"))
    svc = BookingService(session)
    result = await svc.get_free_slots(master, service, date(2026, 4, 20), now=now)
    assert [s.hour for s in result] == [15, 16, 17, 18]
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_services_booking.py -v`
Expected: `ModuleNotFoundError: No module named 'src.services.booking'`.

- [ ] **Step 3: Implement `src/services/booking.py` with `get_free_slots` only**

```python
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Service
from src.repositories.appointments import AppointmentRepository
from src.services.availability import calculate_free_slots


class BookingService:
    """Appointment lifecycle + slot lookup.

    Owns its own commit/rollback on the create paths (`create_pending`,
    `create_manual`) so that the partial unique index on appointments can
    arbitrate concurrent callers via IntegrityError. All other methods
    mutate in-place and rely on the DB middleware to commit on success.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AppointmentRepository(session)

    async def get_free_slots(
        self,
        master: Master,
        service: Service,
        day: date,
        *,
        now: datetime | None = None,
    ) -> list[datetime]:
        tz = ZoneInfo(master.timezone)
        day_start_local = datetime(day.year, day.month, day.day, tzinfo=tz)
        day_start_utc = day_start_local.astimezone(UTC)
        day_end_utc = (day_start_local + timedelta(days=1)).astimezone(UTC)
        appts = await self._repo.list_active_for_day(
            master.id, day_start_utc=day_start_utc, day_end_utc=day_end_utc
        )
        booked = [(a.start_at, a.end_at) for a in appts]
        return calculate_free_slots(
            work_hours=master.work_hours,
            breaks=master.breaks,
            booked=booked,
            day=day,
            tz=tz,
            slot_step_min=master.slot_step_min,
            service_duration_min=service.duration_min,
            now=now,
        )
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_services_booking.py -v`
Expected: 3 passed.

- [ ] **Step 5: Linters**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/services/booking.py tests/test_services_booking.py
git commit -m "feat(booking): BookingService.get_free_slots integrates repo + availability"
```

---

## Task 6: `BookingService.create_pending` + race-condition test

**Files:**
- Modify: `src/services/booking.py` — append `create_pending`.
- Modify: `tests/test_services_booking.py` — append happy-path + race tests.

- [ ] **Step 1: Append happy-path + race tests to `tests/test_services_booking.py`**

```python
# Add these imports at the top of the test file (grouped with existing imports)
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker

from src.exceptions import SlotAlreadyTaken


@pytest.mark.asyncio
async def test_create_pending_persists_with_decision_deadline(
    session: AsyncSession,
) -> None:
    master, client, service = await _seed(session)
    await session.commit()

    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    now = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
    svc = BookingService(session)
    appt = await svc.create_pending(
        master=master, client=client, service=service, start_at=start, now=now
    )

    assert appt.status == "pending"
    assert appt.source == "client_request"
    assert appt.start_at == start
    assert appt.end_at == start + timedelta(minutes=service.duration_min)
    # decision_deadline = now + 120 min (master.decision_timeout_min)
    assert appt.decision_deadline == now + timedelta(minutes=master.decision_timeout_min)


@pytest.mark.asyncio
async def test_create_pending_rejects_duplicate(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()

    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    svc = BookingService(session)
    await svc.create_pending(master=master, client=client, service=service, start_at=start)

    # Re-use the same session — the second insert hits IntegrityError and becomes SlotAlreadyTaken
    with pytest.raises(SlotAlreadyTaken):
        await svc.create_pending(
            master=master, client=client, service=service, start_at=start
        )


@pytest.mark.asyncio
async def test_create_pending_race_one_wins_one_loses(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    # Seed master/client/service via the per-test `session` fixture and commit
    master, client, service = await _seed(session)
    await session.commit()
    # Close the seed session so it doesn't hold locks
    await session.close()

    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)

    async def attempt() -> object:
        async with session_maker() as s:
            svc = BookingService(s)
            try:
                return await svc.create_pending(
                    master=master, client=client, service=service, start_at=start
                )
            except SlotAlreadyTaken as exc:
                return exc

    a, b = await asyncio.gather(attempt(), attempt())
    from src.db.models import Appointment
    wins = [r for r in (a, b) if isinstance(r, Appointment)]
    losses = [r for r in (a, b) if isinstance(r, SlotAlreadyTaken)]
    assert len(wins) == 1
    assert len(losses) == 1
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_services_booking.py -v`
Expected: AttributeError: `'BookingService' object has no attribute 'create_pending'`.

- [ ] **Step 3: Append `create_pending` to `src/services/booking.py`**

Add these imports at the top of the file (grouped with existing):

```python
from sqlalchemy.exc import IntegrityError

from src.db.models import Appointment, Client
from src.exceptions import SlotAlreadyTaken
from src.utils.time import now_utc
```

Append to the `BookingService` class:

```python
    async def create_pending(
        self,
        *,
        master: Master,
        client: Client,
        service: Service,
        start_at: datetime,
        now: datetime | None = None,
    ) -> Appointment:
        """Create a client-requested appointment in `pending` state.

        Commits on success so the unique-index row lock is released for other
        writers. On IntegrityError (slot taken between `get_free_slots` and here),
        rolls back and raises SlotAlreadyTaken — handler should re-render the grid.
        """
        n = now if now is not None else now_utc()
        end_at = start_at + timedelta(minutes=service.duration_min)
        deadline = n + timedelta(minutes=master.decision_timeout_min)
        try:
            appt = await self._repo.create(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at=start_at,
                end_at=end_at,
                status="pending",
                source="client_request",
                decision_deadline=deadline,
            )
            await self._session.commit()
            return appt
        except IntegrityError as exc:
            await self._session.rollback()
            raise SlotAlreadyTaken(str(start_at)) from exc
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_services_booking.py -v`
Expected: 6 passed (3 from Task 5 + 3 new).

- [ ] **Step 5: Linters**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/services/booking.py tests/test_services_booking.py
git commit -m "feat(booking): create_pending with IntegrityError -> SlotAlreadyTaken race guard"
```

---

## Task 7: `BookingService.confirm` / `reject` / `cancel`

**Files:**
- Modify: `src/services/booking.py` — append three methods.
- Modify: `tests/test_services_booking.py` — append tests.

- [ ] **Step 1: Append tests to `tests/test_services_booking.py`**

```python
from src.exceptions import InvalidState, NotFound
from uuid import uuid4


@pytest.mark.asyncio
async def test_confirm_sets_status_and_confirmed_at(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(
        master=master, client=client, service=service, start_at=start
    )

    confirmed_at = datetime(2026, 4, 20, 8, 30, tzinfo=UTC)
    result = await svc.confirm(appt.id, master_id=master.id, now=confirmed_at)
    assert result.status == "confirmed"
    assert result.confirmed_at == confirmed_at


@pytest.mark.asyncio
async def test_confirm_missing_raises_not_found(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    with pytest.raises(NotFound):
        await svc.confirm(uuid4(), master_id=master.id)


@pytest.mark.asyncio
async def test_confirm_non_pending_raises_invalid_state(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(
        master=master, client=client, service=service, start_at=start
    )
    await svc.confirm(appt.id, master_id=master.id)

    with pytest.raises(InvalidState):
        await svc.confirm(appt.id, master_id=master.id)


@pytest.mark.asyncio
async def test_reject_sets_status_and_appends_reason(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(
        master=master, client=client, service=service, start_at=start
    )

    result = await svc.reject(appt.id, master_id=master.id, reason="занят")
    assert result.status == "rejected"
    assert result.comment == "занят"


@pytest.mark.asyncio
async def test_reject_non_pending_raises_invalid_state(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(
        master=master, client=client, service=service, start_at=start
    )
    await svc.reject(appt.id, master_id=master.id)

    with pytest.raises(InvalidState):
        await svc.reject(appt.id, master_id=master.id)


@pytest.mark.asyncio
async def test_cancel_by_client_sets_fields(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(
        master=master, client=client, service=service, start_at=start
    )
    await svc.confirm(appt.id, master_id=master.id)

    cancelled_at = datetime(2026, 4, 20, 8, 0, tzinfo=UTC)
    result = await svc.cancel(appt.id, cancelled_by="client", now=cancelled_at)
    assert result.status == "cancelled"
    assert result.cancelled_at == cancelled_at
    assert result.cancelled_by == "client"


@pytest.mark.asyncio
async def test_cancel_invalid_cancelled_by_raises_value_error(
    session: AsyncSession,
) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(
        master=master, client=client, service=service, start_at=start
    )
    with pytest.raises(ValueError):
        await svc.cancel(appt.id, cancelled_by="nobody")


@pytest.mark.asyncio
async def test_cancel_terminal_status_raises_invalid_state(
    session: AsyncSession,
) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    appt = await svc.create_pending(
        master=master, client=client, service=service, start_at=start
    )
    await svc.cancel(appt.id, cancelled_by="client")

    with pytest.raises(InvalidState):
        await svc.cancel(appt.id, cancelled_by="client")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_services_booking.py -v`
Expected: AttributeError: `'BookingService' object has no attribute 'confirm'`.

- [ ] **Step 3: Append methods to `src/services/booking.py`**

Ensure these imports are at the top (add `UUID`, `NotFound`, `InvalidState`):

```python
from uuid import UUID

from src.exceptions import InvalidState, NotFound, SlotAlreadyTaken  # extend
```

Append to `BookingService`:

```python
    async def confirm(
        self,
        appointment_id: UUID,
        *,
        master_id: UUID,
        now: datetime | None = None,
    ) -> Appointment:
        n = now if now is not None else now_utc()
        appt = await self._repo.get(appointment_id, master_id=master_id)
        if appt is None:
            raise NotFound(str(appointment_id))
        if appt.status != "pending":
            raise InvalidState(f"cannot confirm from status={appt.status!r}")
        appt.status = "confirmed"
        appt.confirmed_at = n
        return appt

    async def reject(
        self,
        appointment_id: UUID,
        *,
        master_id: UUID,
        reason: str | None = None,
    ) -> Appointment:
        appt = await self._repo.get(appointment_id, master_id=master_id)
        if appt is None:
            raise NotFound(str(appointment_id))
        if appt.status != "pending":
            raise InvalidState(f"cannot reject from status={appt.status!r}")
        appt.status = "rejected"
        if reason:
            appt.comment = reason if not appt.comment else f"{appt.comment}\n{reason}"
        return appt

    async def cancel(
        self,
        appointment_id: UUID,
        *,
        cancelled_by: str,
        now: datetime | None = None,
    ) -> Appointment:
        if cancelled_by not in ("client", "master", "system"):
            raise ValueError(f"invalid cancelled_by: {cancelled_by!r}")
        n = now if now is not None else now_utc()
        appt = await self._repo.get(appointment_id)
        if appt is None:
            raise NotFound(str(appointment_id))
        if appt.status in ("cancelled", "rejected", "completed", "no_show"):
            raise InvalidState(f"cannot cancel from status={appt.status!r}")
        appt.status = "cancelled"
        appt.cancelled_at = n
        appt.cancelled_by = cancelled_by
        return appt
```

Note: these three methods mutate the loaded ORM object and return it without calling `session.commit()` — the DB middleware at the handler boundary commits on clean return. Tests that call them directly against the `session` fixture observe the mutation via SQLAlchemy's identity map; a subsequent `session.commit()` persists.

- [ ] **Step 4: Run tests, verify they pass**

Run: `DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_services_booking.py -v`
Expected: 14 passed (6 prior + 8 new).

- [ ] **Step 5: Linters**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/services/booking.py tests/test_services_booking.py
git commit -m "feat(booking): confirm / reject / cancel with NotFound + InvalidState guards"
```

---

## Task 8: `BookingService.create_manual` + race test

**Files:**
- Modify: `src/services/booking.py` — append `create_manual`.
- Modify: `tests/test_services_booking.py` — append tests.

- [ ] **Step 1: Append tests to `tests/test_services_booking.py`**

```python
@pytest.mark.asyncio
async def test_create_manual_is_instantly_confirmed(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    now = datetime(2026, 4, 20, 7, 0, tzinfo=UTC)

    appt = await svc.create_manual(
        master=master, client=client, service=service,
        start_at=start, comment="клиент позвонил", now=now,
    )
    assert appt.status == "confirmed"
    assert appt.source == "master_manual"
    assert appt.confirmed_at == now
    assert appt.comment == "клиент позвонил"
    assert appt.end_at == start + timedelta(minutes=service.duration_min)


@pytest.mark.asyncio
async def test_create_manual_rejects_if_slot_taken(session: AsyncSession) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    svc = BookingService(session)
    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)
    await svc.create_manual(
        master=master, client=client, service=service, start_at=start
    )

    with pytest.raises(SlotAlreadyTaken):
        await svc.create_manual(
            master=master, client=client, service=service, start_at=start
        )


@pytest.mark.asyncio
async def test_create_manual_race_one_wins_one_loses(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    master, client, service = await _seed(session)
    await session.commit()
    await session.close()

    start = datetime(2026, 4, 20, 9, 0, tzinfo=UTC)

    async def attempt() -> object:
        async with session_maker() as s:
            svc = BookingService(s)
            try:
                return await svc.create_manual(
                    master=master, client=client, service=service, start_at=start
                )
            except SlotAlreadyTaken as exc:
                return exc

    a, b = await asyncio.gather(attempt(), attempt())
    from src.db.models import Appointment
    wins = [r for r in (a, b) if isinstance(r, Appointment)]
    losses = [r for r in (a, b) if isinstance(r, SlotAlreadyTaken)]
    assert len(wins) == 1
    assert len(losses) == 1
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_services_booking.py -v`
Expected: AttributeError: `'BookingService' object has no attribute 'create_manual'`.

- [ ] **Step 3: Append `create_manual` to `src/services/booking.py`**

```python
    async def create_manual(
        self,
        *,
        master: Master,
        client: Client,
        service: Service,
        start_at: datetime,
        comment: str | None = None,
        now: datetime | None = None,
    ) -> Appointment:
        """Master-added appointment — instantly `confirmed`.

        Same commit/rollback behaviour as `create_pending` so the partial unique
        index enforces mutual exclusion with concurrent client requests.
        """
        n = now if now is not None else now_utc()
        end_at = start_at + timedelta(minutes=service.duration_min)
        try:
            appt = await self._repo.create(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at=start_at,
                end_at=end_at,
                status="confirmed",
                source="master_manual",
                comment=comment,
                confirmed_at=n,
            )
            await self._session.commit()
            return appt
        except IntegrityError as exc:
            await self._session.rollback()
            raise SlotAlreadyTaken(str(start_at)) from exc
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_services_booking.py -v`
Expected: 17 passed (14 prior + 3 new).

- [ ] **Step 5: Verify coverage target**

Run:
```bash
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" \
  uv run pytest tests/ --cov=src.services.booking --cov=src.services.availability \
  --cov-report=term-missing
```
Expected:
- `src/services/availability.py` — 100%
- `src/services/booking.py` — ≥90%

If booking.py is below 90%, inspect the Missing column and add a targeted test. Do not lower the coverage target.

- [ ] **Step 6: Linters**

Run: `uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/`
Expected: all clean.

- [ ] **Step 7: Commit**

```bash
git add src/services/booking.py tests/test_services_booking.py
git commit -m "feat(booking): create_manual instantly confirmed with same race guard"
```

---

## Task 9: Epic 3 acceptance + tag

No smoke test in Telegram for this epic — all surfaces are internal. Epic 4 will wire the booking service into the client-facing FSM and the master's approval callbacks.

- [ ] **Step 1: Run the full gate**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/ tests/
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" \
  uv run pytest tests/ -v --cov=src --cov-report=term-missing
```

Expected:
- Ruff: 0 errors.
- Ruff format: "already formatted".
- Mypy: `Success: no issues found`.
- Pytest: all tests pass. Coverage:
  - `src/services/availability.py` — 100%.
  - `src/services/booking.py` — ≥90%.
  - `src/repositories/appointments.py` — ≥90%.
  - `src/utils/time.py` — 100%.
  - `src/exceptions.py` — 100% (classes are imported).

- [ ] **Step 2: Tag**

```bash
git tag -a v0.3.0-epic-3 -m "Epic 3 complete: availability, appointments repo, BookingService"
```

Do not push — wait for user approval before `git push origin main && git push origin v0.3.0-epic-3`.

---

## Epic 3 deliverables

- `src/utils/time.py` — tz-aware clock helpers.
- `src/exceptions.py` — `SlotAlreadyTaken`, `NotFound`, `InvalidState`.
- `src/services/availability.py` — pure `calculate_free_slots`, 100% coverage.
- `src/repositories/appointments.py` — CRUD + day-scoped query + pending-past-deadline query.
- `src/services/booking.py` — `get_free_slots`, `create_pending`, `confirm`, `reject`, `cancel`, `create_manual`. Race-condition guard via partial unique index + `IntegrityError → SlotAlreadyTaken`.
- Tests: 12 availability + 8 repo + 17 service = 37 new, none of them mocks. Repo and service tests hit real Postgres; race tests use two concurrent sessions from `session_maker`.

## What comes next (NOT in this plan)

- Reminder scheduling on confirm (Epic 7). `BookingService.confirm` is deliberately minimal today — Epic 7 will wrap it with `ReminderService.schedule_for(appt)`.
- Client-facing booking FSM (Epic 4) — the consumer of `get_free_slots` + `create_pending`.
- Master approval callbacks (Epic 4 or 5).
