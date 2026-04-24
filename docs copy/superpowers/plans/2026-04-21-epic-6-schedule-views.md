# Epic 6 — Schedule Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the master read-oriented schedule surfaces (`/today`, `/tomorrow`, `/week`, `/calendar`, `/client`) plus ability to close out past `confirmed` appointments and edit client notes. Spec: `docs/superpowers/specs/2026-04-21-epic-6-schedule-views-design.md`.

**Architecture:** A shared pure renderer (`src/utils/schedule_format.py`) owns day-schedule text+keyboard; five new handler modules call into it. One new FSM (`MasterView`), three new service methods (`mark_completed`, `mark_no_show`, `update_notes`), one new repository method (`list_for_master_range`). The existing `calendar_keyboard` gains an `allow_past` flag (master uses it for history navigation; client keeps today-forward behaviour). Six new typed callback classes. All new handlers live under `src/handlers/master/` and are gated by the existing master router.

**Tech Stack:** Python 3.12, aiogram 3.x, SQLAlchemy 2.0 async, PostgreSQL 16, pytest-asyncio, mypy --strict, ruff. All UTC in DB, `Asia/Yerevan` conversion at boundaries via `ZoneInfo`.

**Quality gates (run before every commit):**
```bash
ruff check . && ruff format --check . && mypy src/
pytest -q
```

---

## Task 1: `AppointmentRepository.list_for_master_range`

**Files:**
- Modify: `src/repositories/appointments.py`
- Test: `tests/test_repo_appointments_range.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_repo_appointments_range.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.repositories.appointments import AppointmentRepository


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(tg_id=7001, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="C", phone="+37499000001")
    session.add(client)
    svc = Service(master_id=master.id, name="S", duration_min=60)
    session.add(svc)
    await session.flush()
    return master, client, svc


def _mkappt(
    *,
    master_id: object,
    client_id: object,
    service_id: object,
    start: datetime,
    status: str,
) -> Appointment:
    return Appointment(
        master_id=master_id,
        client_id=client_id,
        service_id=service_id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status=status,
        source="master_manual",
    )


@pytest.mark.asyncio
async def test_default_statuses_return_pending_and_confirmed(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    t0 = datetime(2026, 5, 1, 10, tzinfo=UTC)
    for st, hr in [
        ("pending", 10),
        ("confirmed", 11),
        ("cancelled", 12),
        ("rejected", 13),
        ("completed", 14),
        ("no_show", 15),
    ]:
        session.add(
            _mkappt(
                master_id=master.id,
                client_id=client.id,
                service_id=svc.id,
                start=t0.replace(hour=hr),
                status=st,
            )
        )
    await session.flush()

    repo = AppointmentRepository(session)
    rows = await repo.list_for_master_range(
        master.id,
        start_utc=datetime(2026, 5, 1, tzinfo=UTC),
        end_utc=datetime(2026, 5, 2, tzinfo=UTC),
    )
    statuses = sorted(r.status for r in rows)
    assert statuses == ["confirmed", "pending"]


@pytest.mark.asyncio
async def test_explicit_statuses_override_default(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    t0 = datetime(2026, 5, 1, 10, tzinfo=UTC)
    for st, hr in [("confirmed", 10), ("completed", 11), ("no_show", 12)]:
        session.add(
            _mkappt(
                master_id=master.id,
                client_id=client.id,
                service_id=svc.id,
                start=t0.replace(hour=hr),
                status=st,
            )
        )
    await session.flush()

    repo = AppointmentRepository(session)
    rows = await repo.list_for_master_range(
        master.id,
        start_utc=datetime(2026, 5, 1, tzinfo=UTC),
        end_utc=datetime(2026, 5, 2, tzinfo=UTC),
        statuses=("confirmed", "completed", "no_show"),
    )
    assert sorted(r.status for r in rows) == ["completed", "confirmed", "no_show"]


@pytest.mark.asyncio
async def test_range_is_half_open_start_inclusive_end_exclusive(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    start = datetime(2026, 5, 1, 12, tzinfo=UTC)
    session.add(
        _mkappt(
            master_id=master.id,
            client_id=client.id,
            service_id=svc.id,
            start=start,
            status="confirmed",
        )
    )
    await session.flush()

    repo = AppointmentRepository(session)
    included = await repo.list_for_master_range(
        master.id,
        start_utc=start,
        end_utc=start + timedelta(hours=1),
    )
    excluded = await repo.list_for_master_range(
        master.id,
        start_utc=start + timedelta(hours=1),
        end_utc=start + timedelta(hours=2),
    )
    assert len(included) == 1
    assert excluded == []


@pytest.mark.asyncio
async def test_other_masters_excluded(session: AsyncSession) -> None:
    master_a, client_a, svc_a = await _seed(session)
    master_b = Master(tg_id=7002, name="B", timezone="Asia/Yerevan")
    session.add(master_b)
    await session.flush()
    client_b = Client(master_id=master_b.id, name="CB", phone="+37499000099")
    svc_b = Service(master_id=master_b.id, name="SB", duration_min=60)
    session.add_all([client_b, svc_b])
    await session.flush()

    t = datetime(2026, 5, 1, 10, tzinfo=UTC)
    session.add(
        _mkappt(
            master_id=master_a.id,
            client_id=client_a.id,
            service_id=svc_a.id,
            start=t,
            status="confirmed",
        )
    )
    session.add(
        _mkappt(
            master_id=master_b.id,
            client_id=client_b.id,
            service_id=svc_b.id,
            start=t.replace(hour=11),
            status="confirmed",
        )
    )
    await session.flush()

    repo = AppointmentRepository(session)
    rows = await repo.list_for_master_range(
        master_a.id,
        start_utc=datetime(2026, 5, 1, tzinfo=UTC),
        end_utc=datetime(2026, 5, 2, tzinfo=UTC),
    )
    assert len(rows) == 1
    assert rows[0].master_id == master_a.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_repo_appointments_range.py -v`
Expected: FAIL with `AttributeError: 'AppointmentRepository' object has no attribute 'list_for_master_range'`

- [ ] **Step 3: Implement `list_for_master_range`**

Modify `src/repositories/appointments.py`. Add after `list_active_for_month`:

```python
    async def list_for_master_range(
        self,
        master_id: UUID,
        *,
        start_utc: datetime,
        end_utc: datetime,
        statuses: tuple[str, ...] | None = None,
    ) -> list[Appointment]:
        """Range query for master-owned appointments, start_at ∈ [start_utc, end_utc).

        Default status filter: ('pending', 'confirmed') — rows that block a slot.
        Pass an explicit tuple to override (e.g. include 'completed'/'no_show').
        """
        effective = statuses if statuses is not None else ("pending", "confirmed")
        stmt = (
            select(Appointment)
            .where(
                Appointment.master_id == master_id,
                Appointment.status.in_(effective),
                Appointment.start_at >= start_utc,
                Appointment.start_at < end_utc,
            )
            .order_by(Appointment.start_at)
        )
        return list((await self._session.scalars(stmt)).all())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_repo_appointments_range.py -v`
Expected: PASS (4/4)

- [ ] **Step 5: Run full gates**

Run: `ruff check . && ruff format --check . && mypy src/ && pytest -q`
Expected: all green, total test count +4.

- [ ] **Step 6: Commit**

```bash
git add src/repositories/appointments.py tests/test_repo_appointments_range.py
git commit -m "feat(repo): AppointmentRepository.list_for_master_range"
```

---

## Task 2: `ClientRepository.update_notes`

**Files:**
- Modify: `src/repositories/clients.py`
- Test: `tests/test_repo_clients_notes.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_repo_clients_notes.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master
from src.repositories.clients import ClientRepository


async def _seed(session: AsyncSession) -> tuple[Master, Client]:
    master = Master(tg_id=7100, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="A", phone="+37499000111")
    session.add(client)
    await session.flush()
    return master, client


@pytest.mark.asyncio
async def test_update_notes_sets_value(session: AsyncSession) -> None:
    _, client = await _seed(session)
    repo = ClientRepository(session)
    await repo.update_notes(client.id, "аллергия на латекс")
    await session.flush()
    reloaded = await repo.get(client.id)
    assert reloaded is not None
    assert reloaded.notes == "аллергия на латекс"


@pytest.mark.asyncio
async def test_update_notes_clears_on_none(session: AsyncSession) -> None:
    _, client = await _seed(session)
    client.notes = "old"
    await session.flush()

    repo = ClientRepository(session)
    await repo.update_notes(client.id, None)
    await session.flush()
    reloaded = await repo.get(client.id)
    assert reloaded is not None
    assert reloaded.notes is None


@pytest.mark.asyncio
async def test_update_notes_empty_string_clears(session: AsyncSession) -> None:
    _, client = await _seed(session)
    client.notes = "old"
    await session.flush()

    repo = ClientRepository(session)
    await repo.update_notes(client.id, "")
    await session.flush()
    reloaded = await repo.get(client.id)
    assert reloaded is not None
    assert reloaded.notes is None


@pytest.mark.asyncio
async def test_update_notes_noop_on_unknown_client(session: AsyncSession) -> None:
    from uuid import uuid4

    repo = ClientRepository(session)
    # Should not raise.
    await repo.update_notes(uuid4(), "x")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_repo_clients_notes.py -v`
Expected: FAIL with `AttributeError: 'ClientRepository' object has no attribute 'update_notes'`

- [ ] **Step 3: Implement `update_notes`**

Modify `src/repositories/clients.py`. Add at the end of the class:

```python
    async def update_notes(self, client_id: UUID, notes: str | None) -> None:
        """Set `Client.notes`. Empty string or None → stored as NULL."""
        client = await self.get(client_id)
        if client is None:
            return
        cleaned = notes.strip() if notes else None
        client.notes = cleaned if cleaned else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_repo_clients_notes.py -v`
Expected: PASS (4/4)

- [ ] **Step 5: Run full gates**

Run: `ruff check . && ruff format --check . && mypy src/ && pytest -q`

- [ ] **Step 6: Commit**

```bash
git add src/repositories/clients.py tests/test_repo_clients_notes.py
git commit -m "feat(repo): ClientRepository.update_notes"
```

---

## Task 3: `BookingService.mark_completed` and `mark_no_show`

**Files:**
- Modify: `src/services/booking.py`
- Test: `tests/test_services_booking_mark.py` (new)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_services_booking_mark.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.exceptions import InvalidState, NotFound
from src.services.booking import BookingService


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(tg_id=7201, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="C", phone="+37499001001")
    svc = Service(master_id=master.id, name="S", duration_min=60)
    session.add_all([client, svc])
    await session.flush()
    return master, client, svc


def _mk_confirmed(
    *, master: Master, client: Client, svc: Service, start: datetime
) -> Appointment:
    return Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=svc.id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status="confirmed",
        source="master_manual",
        confirmed_at=start - timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_mark_completed_promotes_past_confirmed(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    now = datetime(2026, 5, 2, 12, tzinfo=UTC)
    appt = _mk_confirmed(master=master, client=client, svc=svc, start=now - timedelta(hours=3))
    session.add(appt)
    await session.flush()

    svc_b = BookingService(session)
    updated = await svc_b.mark_completed(appt.id, master=master, now=now)
    assert updated.status == "completed"


@pytest.mark.asyncio
async def test_mark_no_show_promotes_past_confirmed(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    now = datetime(2026, 5, 2, 12, tzinfo=UTC)
    appt = _mk_confirmed(master=master, client=client, svc=svc, start=now - timedelta(hours=3))
    session.add(appt)
    await session.flush()

    svc_b = BookingService(session)
    updated = await svc_b.mark_no_show(appt.id, master=master, now=now)
    assert updated.status == "no_show"


@pytest.mark.asyncio
async def test_mark_completed_refuses_future_end(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    now = datetime(2026, 5, 2, 12, tzinfo=UTC)
    # starts now, ends in +60 min → end_at > now
    appt = _mk_confirmed(master=master, client=client, svc=svc, start=now)
    session.add(appt)
    await session.flush()

    svc_b = BookingService(session)
    with pytest.raises(InvalidState):
        await svc_b.mark_completed(appt.id, master=master, now=now)


@pytest.mark.asyncio
async def test_mark_completed_refuses_non_confirmed(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    now = datetime(2026, 5, 2, 12, tzinfo=UTC)
    appt = _mk_confirmed(master=master, client=client, svc=svc, start=now - timedelta(hours=3))
    appt.status = "completed"
    session.add(appt)
    await session.flush()

    svc_b = BookingService(session)
    with pytest.raises(InvalidState):
        await svc_b.mark_completed(appt.id, master=master, now=now)


@pytest.mark.asyncio
async def test_mark_completed_wrong_master_is_not_found(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    other = Master(tg_id=7202, name="O", timezone="Asia/Yerevan")
    session.add(other)
    await session.flush()
    now = datetime(2026, 5, 2, 12, tzinfo=UTC)
    appt = _mk_confirmed(master=master, client=client, svc=svc, start=now - timedelta(hours=3))
    session.add(appt)
    await session.flush()

    svc_b = BookingService(session)
    with pytest.raises(NotFound):
        await svc_b.mark_completed(appt.id, master=other, now=now)


@pytest.mark.asyncio
async def test_mark_no_show_missing_id(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    svc_b = BookingService(session)
    with pytest.raises(NotFound):
        await svc_b.mark_no_show(uuid4(), master=master, now=datetime.now(UTC))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_services_booking_mark.py -v`
Expected: FAIL with `AttributeError` on `mark_completed`/`mark_no_show`.

- [ ] **Step 3: Implement the two methods**

Modify `src/services/booking.py`. Add after `cancel_by_client`:

```python
    async def _mark_past(
        self,
        appointment_id: UUID,
        *,
        master: Master,
        new_status: str,
        now: datetime | None,
    ) -> Appointment:
        n = now if now is not None else now_utc()
        appt = await self._repo.get(appointment_id, master_id=master.id)
        if appt is None:
            raise NotFound(str(appointment_id))
        if appt.status != "confirmed":
            raise InvalidState(f"cannot {new_status} from status={appt.status!r}")
        if appt.end_at > n:
            raise InvalidState("appointment has not ended yet")
        appt.status = new_status
        return appt

    async def mark_completed(
        self,
        appointment_id: UUID,
        *,
        master: Master,
        now: datetime | None = None,
    ) -> Appointment:
        """Promote a confirmed, already-ended appointment to `completed`."""
        return await self._mark_past(
            appointment_id, master=master, new_status="completed", now=now
        )

    async def mark_no_show(
        self,
        appointment_id: UUID,
        *,
        master: Master,
        now: datetime | None = None,
    ) -> Appointment:
        """Same preconditions as mark_completed; sets status='no_show'."""
        return await self._mark_past(
            appointment_id, master=master, new_status="no_show", now=now
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_services_booking_mark.py -v`
Expected: PASS (6/6)

- [ ] **Step 5: Run full gates**

Run: `ruff check . && ruff format --check . && mypy src/ && pytest -q`

- [ ] **Step 6: Commit**

```bash
git add src/services/booking.py tests/test_services_booking_mark.py
git commit -m "feat(booking): mark_completed and mark_no_show for past confirmed"
```

---

## Task 4: Strings (RU + HY mirror)

**Files:**
- Modify: `src/strings.py`

Purpose: add all Epic 6 keys up front in RU, mirror them to HY (identical to RU for now — user replaces HY text in Task 14). Handlers/keyboards in later tasks reference these via `strings.KEY`.

- [ ] **Step 1: Add RU keys**

Open `src/strings.py`. Append the following block to `_RU` (immediately before the closing `}`):

```python
    # --- Epic 6: schedule views ---
    "SCHED_DAY_HEADER": "📅 {weekday} {dd} {mon}",
    "SCHED_WORK_HOURS_LINE": "🕐 Рабочие часы: {start}–{end}",
    "SCHED_DAY_OFF_LINE": "🕐 Сегодня выходной",
    "SCHED_APPTS_SECTION": "\n📋 Записи ({count}):",
    "SCHED_APPTS_EMPTY": "\n📋 Записей нет.",
    "SCHED_APPT_LINE": "{emoji} {time}  {client} · {service}",
    "SCHED_FREE_SECTION": "\n🆓 Свободно:",
    "SCHED_FREE_NONE": "\n🆓 Свободных слотов нет.",
    "SCHED_STATUS_PENDING": "⏳",
    "SCHED_STATUS_CONFIRMED": "✅",
    "SCHED_STATUS_COMPLETED": "✅",
    "SCHED_STATUS_NO_SHOW": "❌",
    "DAY_NAV_TODAY": "⬅ Сегодня",
    "DAY_NAV_TOMORROW": "📅 Завтра",
    "DAY_NAV_WEEK": "🗓 Неделя",
    "DAY_NAV_CALENDAR": "🗓 Календарь",
    "DAY_NAV_ADD": "➕ Добавить",
    "DAY_NAV_BACK_TO_WEEK": "⬅ Назад в неделю",
    "DAY_NAV_BACK_TO_CALENDAR": "⬅ Назад в календарь",
    "MARK_PAST_PRESENT": "✅ {time} {short}",
    "MARK_PAST_NO_SHOW": "❌ {time} {short}",
    "MARK_PAST_OK_COMPLETED": "Отмечено: был",
    "MARK_PAST_OK_NO_SHOW": "Отмечено: не пришёл",
    "MARK_PAST_NOT_AVAILABLE": "Запись недоступна",
    "MARK_PAST_NOT_ENDED": "Ещё не закончилась",
    "MARK_PAST_ALREADY_CLOSED": "Уже помечена",
    "WEEK_HEADER": "🗓 Неделя с {dd} {mon}",
    "WEEK_DAY_LINE": "{wd} {dd}.{mm}  {count} зап  {bar}  {pct}%",
    "WEEK_DAY_LINE_OFF": "{wd} {dd}.{mm}  выходной  {bar}",
    "WEEK_BTN_DAY": "{wd} {dd}",
    "CLIENT_SEARCH_PROMPT": "Имя или телефон клиента:",
    "CLIENT_SEARCH_TOO_SHORT": "Минимум 2 символа. Попробуй ещё.",
    "CLIENT_SEARCH_EMPTY": "Никого не нашёл. Попробуй ещё.",
    "CLIENT_PAGE_HEADER": "👤 {name}\n📞 {phone}",
    "CLIENT_PAGE_NOTES_TITLE": "\n\n📝 Заметки:\n{notes}",
    "CLIENT_PAGE_NOTES_EMPTY": "_не указано_",
    "CLIENT_PAGE_HISTORY_TITLE": "\n\n📊 История ({count} записей):",
    "CLIENT_PAGE_HISTORY_EMPTY": "\n\n📊 Истории пока нет.",
    "CLIENT_PAGE_HISTORY_LINE": "{emoji} {dd}.{mm}  {time}  {service}{suffix}",
    "CLIENT_PAGE_HISTORY_MORE": "…и ещё {n}",
    "CLIENT_PAGE_SUFFIX_FUTURE": " · будущая",
    "CLIENT_PAGE_SUFFIX_CANCELLED": " · отменена",
    "CLIENT_PAGE_SUFFIX_REJECTED": " · отклонена",
    "CLIENT_PAGE_BTN_EDIT_NOTES": "✏️ Редактировать заметки",
    "CLIENT_PAGE_BTN_ADD_APPT": "➕ Добавить запись",
    "CLIENT_PAGE_NOT_FOUND": "Клиент не найден.",
    "CLIENT_NOTES_PROMPT": "Новые заметки (или отправь `-` чтобы очистить):",
    "CLIENT_NOTES_SAVED": "Сохранено.",
```

- [ ] **Step 2: Add HY keys (mirror RU)**

Append the same block to `_HY` (immediately before its closing `}`) — character-identical to the RU block above. User will translate in Task 14.

- [ ] **Step 3: Write a guardrail test that confirms keys resolve under both langs**

Create `tests/test_strings_epic6_keys.py`:

```python
from __future__ import annotations

from src.strings import DEFAULT_LANG, set_current_lang, strings

_KEYS = [
    "SCHED_DAY_HEADER",
    "SCHED_WORK_HOURS_LINE",
    "SCHED_DAY_OFF_LINE",
    "SCHED_APPTS_SECTION",
    "SCHED_APPTS_EMPTY",
    "SCHED_APPT_LINE",
    "SCHED_FREE_SECTION",
    "SCHED_FREE_NONE",
    "DAY_NAV_TODAY",
    "DAY_NAV_TOMORROW",
    "DAY_NAV_WEEK",
    "DAY_NAV_CALENDAR",
    "DAY_NAV_ADD",
    "DAY_NAV_BACK_TO_WEEK",
    "DAY_NAV_BACK_TO_CALENDAR",
    "MARK_PAST_PRESENT",
    "MARK_PAST_NO_SHOW",
    "MARK_PAST_OK_COMPLETED",
    "MARK_PAST_OK_NO_SHOW",
    "MARK_PAST_NOT_AVAILABLE",
    "MARK_PAST_NOT_ENDED",
    "MARK_PAST_ALREADY_CLOSED",
    "WEEK_HEADER",
    "WEEK_DAY_LINE",
    "WEEK_DAY_LINE_OFF",
    "WEEK_BTN_DAY",
    "CLIENT_SEARCH_PROMPT",
    "CLIENT_SEARCH_TOO_SHORT",
    "CLIENT_SEARCH_EMPTY",
    "CLIENT_PAGE_HEADER",
    "CLIENT_PAGE_NOTES_TITLE",
    "CLIENT_PAGE_NOTES_EMPTY",
    "CLIENT_PAGE_HISTORY_TITLE",
    "CLIENT_PAGE_HISTORY_EMPTY",
    "CLIENT_PAGE_HISTORY_LINE",
    "CLIENT_PAGE_HISTORY_MORE",
    "CLIENT_PAGE_SUFFIX_FUTURE",
    "CLIENT_PAGE_SUFFIX_CANCELLED",
    "CLIENT_PAGE_SUFFIX_REJECTED",
    "CLIENT_PAGE_BTN_EDIT_NOTES",
    "CLIENT_PAGE_BTN_ADD_APPT",
    "CLIENT_PAGE_NOT_FOUND",
    "CLIENT_NOTES_PROMPT",
    "CLIENT_NOTES_SAVED",
]


def test_epic6_keys_resolve_ru() -> None:
    set_current_lang("ru")
    try:
        for k in _KEYS:
            assert isinstance(getattr(strings, k), str), k
    finally:
        set_current_lang(DEFAULT_LANG)


def test_epic6_keys_resolve_hy() -> None:
    set_current_lang("hy")
    try:
        for k in _KEYS:
            assert isinstance(getattr(strings, k), str), k
    finally:
        set_current_lang(DEFAULT_LANG)
```

- [ ] **Step 4: Run tests and gates**

Run: `pytest tests/test_strings_epic6_keys.py -v && ruff check . && ruff format --check . && mypy src/`
Expected: all green. If ruff complains about line length on a single long string, wrap it as `(...)` like existing entries.

- [ ] **Step 5: Commit**

```bash
git add src/strings.py tests/test_strings_epic6_keys.py
git commit -m "feat(strings): Epic 6 schedule-view keys (RU, HY mirror)"
```

---

## Task 5: New callback data classes

**Files:**
- Create: `src/callback_data/schedule.py`
- Create: `src/callback_data/mark_past.py`
- Create: `src/callback_data/master_calendar.py`
- Create: `src/callback_data/client_page.py`

Each class uses a short prefix to stay well under the 64-byte limit. UUID costs 36 bytes; prefix + separators ≤ 10 bytes; enum/int fields fit in the remainder.

- [ ] **Step 1: Write the import-smoke test**

Create `tests/test_callbacks_epic6.py`:

```python
from __future__ import annotations

from uuid import uuid4

from src.callback_data.client_page import (
    ClientAddApptCallback,
    ClientNotesEditCallback,
    ClientPickCallback,
)
from src.callback_data.mark_past import MarkPastCallback
from src.callback_data.master_calendar import MasterCalendarCallback
from src.callback_data.schedule import DayNavCallback, DayPickCallback


def test_pack_under_64_bytes() -> None:
    cid = uuid4()
    for payload in [
        DayPickCallback(ymd="2026-04-25").pack(),
        DayNavCallback(action="today").pack(),
        MarkPastCallback(action="present", appointment_id=cid).pack(),
        MasterCalendarCallback(action="pick", year=2026, month=5, day=3).pack(),
        ClientPickCallback(client_id=cid).pack(),
        ClientNotesEditCallback(client_id=cid).pack(),
        ClientAddApptCallback(client_id=cid).pack(),
    ]:
        assert len(payload.encode("utf-8")) <= 64, payload


def test_roundtrip_mark_past() -> None:
    cid = uuid4()
    packed = MarkPastCallback(action="no_show", appointment_id=cid).pack()
    restored = MarkPastCallback.unpack(packed)
    assert restored.action == "no_show"
    assert restored.appointment_id == cid


def test_prefix_does_not_collide_with_client_calendar() -> None:
    # Existing CalendarCallback has prefix "cal"; MasterCalendarCallback uses "mca".
    mca = MasterCalendarCallback(action="noop", year=2026, month=1, day=0).pack()
    assert mca.startswith("mca:")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_callbacks_epic6.py -v`
Expected: FAIL (imports raise `ModuleNotFoundError`).

- [ ] **Step 3: Create the callback modules**

`src/callback_data/schedule.py`:

```python
from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class DayPickCallback(CallbackData, prefix="dpk"):
    """A /week day button → render that day's schedule."""

    ymd: str  # ISO YYYY-MM-DD


class DayNavCallback(CallbackData, prefix="dnv"):
    """Day-schedule bottom-bar navigation: today / tomorrow / week / calendar."""

    action: Literal["today", "tomorrow", "week", "calendar", "add"]
```

`src/callback_data/mark_past.py`:

```python
from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class MarkPastCallback(CallbackData, prefix="mpa"):
    """Mark a past `confirmed` appointment as `completed` or `no_show`."""

    action: Literal["present", "no_show"]
    appointment_id: UUID
```

`src/callback_data/master_calendar.py`:

```python
from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class MasterCalendarCallback(CallbackData, prefix="mca"):
    """Master-side calendar cell / nav. Distinct prefix from client's CalendarCallback."""

    action: Literal["pick", "nav", "noop"]
    year: int
    month: int
    day: int = 0
```

`src/callback_data/client_page.py`:

```python
from __future__ import annotations

from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class ClientPickCallback(CallbackData, prefix="cpk"):
    """Row in `/client` search results → open client page."""

    client_id: UUID


class ClientNotesEditCallback(CallbackData, prefix="cne"):
    """Button on client page → enter notes-edit FSM."""

    client_id: UUID


class ClientAddApptCallback(CallbackData, prefix="caa"):
    """Button on client page → enter MasterAdd FSM with client pre-picked."""

    client_id: UUID
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_callbacks_epic6.py -v`
Expected: PASS (3/3)

- [ ] **Step 5: Run full gates**

Run: `ruff check . && ruff format --check . && mypy src/ && pytest -q`

- [ ] **Step 6: Commit**

```bash
git add src/callback_data/schedule.py src/callback_data/mark_past.py src/callback_data/master_calendar.py src/callback_data/client_page.py tests/test_callbacks_epic6.py
git commit -m "feat(callbacks): Epic 6 schedule/mark-past/master-calendar/client-page"
```

---

## Task 6: `MasterView` FSM

**Files:**
- Create: `src/fsm/master_view.py`

- [ ] **Step 1: Create the FSM module**

`src/fsm/master_view.py`:

```python
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MasterView(StatesGroup):
    """States for the /client flow: search query, then editing notes."""

    SearchingClient = State()
    EditingNotes = State()
```

- [ ] **Step 2: Smoke-test the import**

Create `tests/test_fsm_master_view.py`:

```python
from __future__ import annotations

from src.fsm.master_view import MasterView


def test_states_exist() -> None:
    assert MasterView.SearchingClient.state is not None
    assert MasterView.EditingNotes.state is not None
    assert MasterView.SearchingClient.state != MasterView.EditingNotes.state
```

- [ ] **Step 3: Run tests and gates**

Run: `pytest tests/test_fsm_master_view.py -v && ruff check . && mypy src/`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/fsm/master_view.py tests/test_fsm_master_view.py
git commit -m "feat(fsm): MasterView states (SearchingClient, EditingNotes)"
```

---

## Task 7: `calendar_keyboard` `allow_past` parameter

**Files:**
- Modify: `src/keyboards/calendar.py`
- Test: `tests/test_keyboards_calendar_allow_past.py` (new)

Context: current behaviour blocks nav into months strictly before `today.replace(day=1)` and keeps past-day cells as noop. For `/calendar` (master view) we want arbitrary-month navigation AND clickable past days. Keep default `False` so existing client callers are unaffected.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_keyboards_calendar_allow_past.py`:

```python
from __future__ import annotations

from datetime import date

from src.callback_data.calendar import CalendarCallback
from src.keyboards.calendar import calendar_keyboard


def _collect_callbacks(kb: object) -> list[str]:
    out: list[str] = []
    rows = getattr(kb, "inline_keyboard", [])
    for row in rows:
        for btn in row:
            cd = getattr(btn, "callback_data", None)
            if cd is not None:
                out.append(str(cd))
    return out


def test_default_blocks_prev_from_current_month() -> None:
    today = date(2026, 5, 10)
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): 5 for d in range(1, 32)},
        today=today,
    )
    # Prev button renders as noop when at current month boundary (existing behaviour).
    packed = _collect_callbacks(kb)
    prev_nav = [
        p for p in packed
        if p.startswith("cal:nav") and ":4:" in p
    ]
    assert prev_nav == []


def test_allow_past_enables_prev_nav_into_prior_months() -> None:
    today = date(2026, 5, 10)
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): 5 for d in range(1, 32)},
        today=today,
        allow_past=True,
    )
    packed = _collect_callbacks(kb)
    # Expect a nav callback for previous month (April 2026).
    assert any(CalendarCallback(action="nav", year=2026, month=4).pack() == p for p in packed)


def test_allow_past_makes_past_days_clickable() -> None:
    today = date(2026, 5, 10)
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): 5 for d in range(1, 32)},
        today=today,
        allow_past=True,
    )
    packed = _collect_callbacks(kb)
    # Day 3 is in the past; should render as pick, not noop.
    pick = CalendarCallback(action="pick", year=2026, month=5, day=3).pack()
    noop_day = CalendarCallback(action="noop", year=2026, month=5, day=0).pack()
    assert pick in packed
    # Noop cells carry day=0; past day with allow_past should NOT be represented as noop_day.
    # (Other noop cells still exist for empty grid slots — we only check 'pick' exists.)


def test_default_past_days_remain_noop() -> None:
    today = date(2026, 5, 10)
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): 5 for d in range(1, 32)},
        today=today,
    )
    packed = _collect_callbacks(kb)
    # Day 3 (past) should NOT be clickable under default behaviour.
    pick = CalendarCallback(action="pick", year=2026, month=5, day=3).pack()
    assert pick not in packed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_keyboards_calendar_allow_past.py -v`
Expected: FAIL — `allow_past` parameter unknown.

- [ ] **Step 3: Patch `calendar_keyboard`**

Modify `src/keyboards/calendar.py`. Update the signature and past-handling logic:

```python
def calendar_keyboard(
    *,
    month: date,
    loads: dict[date, int],
    today: date,
    allow_past: bool = False,
) -> InlineKeyboardMarkup:
    """Render a month grid with emoji-coded availability.

    `loads` must contain an entry for every day of `month`; -1 encodes "off",
    0 = full, 1..4 = tight, ≥5 = free. Past days render as ⚫ without a pick
    callback unless `allow_past=True` (master calendar view).
    """
    year, month_num = month.year, month.month
    month_name = strings.MONTH_NAMES[month_num - 1]

    prev_shift = _shift_month(month, -1)
    next_shift = _shift_month(month, +1)
    can_prev = allow_past or _months_between(today.replace(day=1), prev_shift) >= 0
    can_next = _months_between(today.replace(day=1), next_shift) <= MAX_MONTHS_AHEAD
```

And change the day-cell guard:

```python
    for day in range(1, days_in_month + 1):
        d = date(year, month_num, day)
        count = loads.get(d, -1)
        load = _classify(count)
        emoji = _EMOJI[load]
        label = f"{emoji}{day}"
        is_past_locked = d < today and not allow_past
        if is_past_locked or load == "off":
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_keyboards_calendar_allow_past.py tests/test_keyboards_calendar.py -v` (the second file is the existing suite; confirm no regression)
Expected: PASS on both.

- [ ] **Step 5: Run full gates**

Run: `ruff check . && ruff format --check . && mypy src/ && pytest -q`

- [ ] **Step 6: Commit**

```bash
git add src/keyboards/calendar.py tests/test_keyboards_calendar_allow_past.py
git commit -m "feat(kb): calendar_keyboard allow_past for master history nav"
```

---

## Task 8: Pure day-schedule renderer

**Files:**
- Create: `src/utils/schedule_format.py`
- Test: `tests/test_utils_schedule_format.py` (new)

The renderer is pure (no DB, no clock, no bot). Handler passes in `appts`, `work_hours`, `breaks`, `tz`, `slot_step_min`, `now`, `day_nav`, and gets back `(text, keyboard)`. Free slots are the master's grid intersected with work windows minus breaks minus booked intervals (service-agnostic; every grid point not currently blocked).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_utils_schedule_format.py`:

```python
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton

from src.db.models import Appointment
from src.utils.schedule_format import render_day_schedule

_TZ = ZoneInfo("Asia/Yerevan")


def _appt(
    *,
    aid: UUID | None = None,
    mid: UUID | None = None,
    cid: UUID | None = None,
    sid: UUID | None = None,
    start_local: datetime,
    duration_min: int = 60,
    status: str = "confirmed",
) -> Appointment:
    start_utc = start_local.astimezone(UTC)
    a = Appointment(
        master_id=mid or uuid4(),
        client_id=cid or uuid4(),
        service_id=sid or uuid4(),
        start_at=start_utc,
        end_at=start_utc + timedelta(minutes=duration_min),
        status=status,
        source="master_manual",
    )
    if aid is not None:
        a.id = aid
    return a


_WH = {"wed": [["10:00", "19:00"]]}
_BR = {"wed": [["13:00", "14:00"]]}


def test_day_off_renders_short() -> None:
    d = date(2026, 4, 26)  # Sunday
    text, kb = render_day_schedule(
        d=d,
        appts=[],
        client_names={},
        service_names={},
        work_hours={"sun": []},
        breaks={},
        tz=_TZ,
        slot_step_min=20,
        now=datetime(2026, 4, 26, 8, tzinfo=_TZ).astimezone(UTC),
        day_nav=[],
    )
    assert "выходной" in text.lower() or "Сегодня выходной" in text
    assert kb is not None


def test_free_slots_exclude_breaks_and_booked() -> None:
    d = date(2026, 4, 22)  # Wednesday
    appts = [
        _appt(start_local=datetime(2026, 4, 22, 10, tzinfo=_TZ), duration_min=60, status="confirmed"),
        _appt(start_local=datetime(2026, 4, 22, 15, tzinfo=_TZ), duration_min=60, status="pending"),
    ]
    names_c = {a.client_id: "Анна" for a in appts}
    names_s = {a.service_id: "Стрижка" for a in appts}
    text, _ = render_day_schedule(
        d=d,
        appts=appts,
        client_names=names_c,
        service_names=names_s,
        work_hours=_WH,
        breaks=_BR,
        tz=_TZ,
        slot_step_min=20,
        now=datetime(2026, 4, 22, 9, tzinfo=_TZ).astimezone(UTC),
        day_nav=[],
    )
    # Work hours 10-19, break 13-14. Booked 10-11, 15-16.
    # Grid at 20-min step from 10:00..18:40.
    # Expect 11:00 onwards until 12:40, then 14:00..14:40, then 16:00..18:40 (service-agnostic, every step).
    assert "11:00" in text
    assert "10:00" not in text.split("🆓")[1] if "🆓" in text else True
    assert "13:00" not in text.split("🆓")[1] if "🆓" in text else True
    assert "15:00" not in text.split("🆓")[1] if "🆓" in text else True


def test_mark_past_buttons_appear_for_past_confirmed_only() -> None:
    d = date(2026, 4, 22)
    past_appt = _appt(
        start_local=datetime(2026, 4, 22, 10, tzinfo=_TZ),
        duration_min=60,
        status="confirmed",
    )
    future_appt = _appt(
        start_local=datetime(2026, 4, 22, 17, tzinfo=_TZ),
        duration_min=60,
        status="confirmed",
    )
    pending_past = _appt(
        start_local=datetime(2026, 4, 22, 11, tzinfo=_TZ),
        duration_min=60,
        status="pending",
    )
    appts = [past_appt, pending_past, future_appt]
    names_c = {a.client_id: "Клиент" for a in appts}
    names_s = {a.service_id: "Услуга" for a in appts}
    now = datetime(2026, 4, 22, 13, tzinfo=_TZ).astimezone(UTC)

    _, kb = render_day_schedule(
        d=d,
        appts=appts,
        client_names=names_c,
        service_names=names_s,
        work_hours=_WH,
        breaks=_BR,
        tz=_TZ,
        slot_step_min=20,
        now=now,
        day_nav=[],
    )
    packed = [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if isinstance(btn, InlineKeyboardButton) and btn.callback_data
    ]
    # Mark-past callback prefix is "mpa".
    mpa = [p for p in packed if p.startswith("mpa:")]
    # Exactly 2 buttons (present + no_show) for the one past_confirmed.
    assert len(mpa) == 2


def test_day_nav_rows_are_appended_above_mark_buttons() -> None:
    d = date(2026, 4, 22)
    past_appt = _appt(
        start_local=datetime(2026, 4, 22, 10, tzinfo=_TZ),
        duration_min=60,
        status="confirmed",
    )
    nav = [[InlineKeyboardButton(text="X", callback_data="nav_x")]]
    _, kb = render_day_schedule(
        d=d,
        appts=[past_appt],
        client_names={past_appt.client_id: "N"},
        service_names={past_appt.service_id: "S"},
        work_hours=_WH,
        breaks=_BR,
        tz=_TZ,
        slot_step_min=20,
        now=datetime(2026, 4, 22, 13, tzinfo=_TZ).astimezone(UTC),
        day_nav=nav,
    )
    rows = kb.inline_keyboard
    # First row should be the nav row (callback_data == "nav_x").
    assert rows[0][0].callback_data == "nav_x"
    # The mark-past row follows.
    assert any(
        btn.callback_data and btn.callback_data.startswith("mpa:")
        for row in rows[1:]
        for btn in row
    )


def test_cancelled_and_rejected_appts_excluded_from_text() -> None:
    d = date(2026, 4, 22)
    cancelled = _appt(
        start_local=datetime(2026, 4, 22, 10, tzinfo=_TZ),
        status="cancelled",
    )
    rejected = _appt(
        start_local=datetime(2026, 4, 22, 11, tzinfo=_TZ),
        status="rejected",
    )
    kept = _appt(
        start_local=datetime(2026, 4, 22, 12, tzinfo=_TZ),
        status="confirmed",
    )
    appts = [cancelled, rejected, kept]
    names_c = {a.client_id: f"C{i}" for i, a in enumerate(appts)}
    names_s = {a.service_id: f"S{i}" for i, a in enumerate(appts)}
    text, _ = render_day_schedule(
        d=d,
        appts=appts,
        client_names=names_c,
        service_names=names_s,
        work_hours=_WH,
        breaks=_BR,
        tz=_TZ,
        slot_step_min=20,
        now=datetime(2026, 4, 22, 9, tzinfo=_TZ).astimezone(UTC),
        day_nav=[],
    )
    # Only one appointment line with 12:00.
    assert "12:00" in text
    assert "10:00" not in text  # cancelled stripped
    assert "11:00" not in text  # rejected stripped
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_utils_schedule_format.py -v`
Expected: FAIL — module does not exist yet.

- [ ] **Step 3: Implement the renderer**

Create `src/utils/schedule_format.py`:

```python
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Iterable
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.mark_past import MarkPastCallback
from src.db.models import Appointment
from src.services.availability import WEEKDAYS
from src.strings import strings

_VISIBLE_STATUSES: frozenset[str] = frozenset(
    {"pending", "confirmed", "completed", "no_show"}
)

_STATUS_EMOJI: dict[str, str] = {
    "pending": "⏳",
    "confirmed": "✅",
    "completed": "✅",
    "no_show": "❌",
}


def _parse_hhmm(raw: list[list[str]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in raw:
        sh, sm = s.split(":")
        eh, em = e.split(":")
        out.append((int(sh) * 60 + int(sm), int(eh) * 60 + int(em)))
    return out


def _subtract(
    windows: list[tuple[int, int]], cuts: Iterable[tuple[int, int]]
) -> list[tuple[int, int]]:
    result = list(windows)
    for cs, ce in cuts:
        if ce <= cs:
            continue
        nxt: list[tuple[int, int]] = []
        for ws, we in result:
            if ce <= ws or cs >= we:
                nxt.append((ws, we))
                continue
            if cs > ws:
                nxt.append((ws, cs))
            if ce < we:
                nxt.append((ce, we))
        result = nxt
    return result


def _day_nav_rows(day_nav: list[list[InlineKeyboardButton]]) -> list[list[InlineKeyboardButton]]:
    return list(day_nav)


def _format_month_short(d: date) -> str:
    # 1-indexed short month from existing RU/HY month names (trim to 3 chars for brevity).
    return str(strings.MONTH_NAMES[d.month - 1])[:3].lower()


def _weekday_short(d: date) -> str:
    return str(strings.WEEKDAY_SHORT[d.weekday()])


def render_day_schedule(
    *,
    d: date,
    appts: list[Appointment],
    client_names: dict[UUID, str],
    service_names: dict[UUID, str],
    work_hours: dict[str, list[list[str]]],
    breaks: dict[str, list[list[str]]],
    tz: ZoneInfo,
    slot_step_min: int,
    now: datetime,
    day_nav: list[list[InlineKeyboardButton]],
) -> tuple[str, InlineKeyboardMarkup]:
    """Assemble text + keyboard for one day's schedule.

    Pure function: no DB, no bot, no wall clock (caller supplies `now`).
    """
    visible = [a for a in appts if a.status in _VISIBLE_STATUSES]
    visible.sort(key=lambda a: a.start_at)

    weekday_key = WEEKDAYS[d.weekday()]
    work_raw = work_hours.get(weekday_key) or []
    breaks_raw = breaks.get(weekday_key) or []

    header = strings.SCHED_DAY_HEADER.format(
        weekday=_weekday_short(d),
        dd=f"{d.day:02d}",
        mon=_format_month_short(d),
    )
    if not work_raw:
        hours_line = strings.SCHED_DAY_OFF_LINE
    else:
        start_min, end_min = _parse_hhmm(work_raw)[0]
        last_end = _parse_hhmm(work_raw)[-1][1]
        hours_line = strings.SCHED_WORK_HOURS_LINE.format(
            start=f"{start_min // 60:02d}:{start_min % 60:02d}",
            end=f"{last_end // 60:02d}:{last_end % 60:02d}",
        )

    lines = [header, hours_line]

    if visible:
        lines.append(strings.SCHED_APPTS_SECTION.format(count=len(visible)))
        for a in visible:
            local = a.start_at.astimezone(tz)
            emoji = _STATUS_EMOJI.get(a.status, "•")
            lines.append(
                strings.SCHED_APPT_LINE.format(
                    emoji=emoji,
                    time=f"{local.hour:02d}:{local.minute:02d}",
                    client=client_names.get(a.client_id, "—"),
                    service=service_names.get(a.service_id, "—"),
                )
            )
    else:
        lines.append(strings.SCHED_APPTS_EMPTY)

    free_slots: list[datetime] = []
    if work_raw:
        day_start_local = datetime(d.year, d.month, d.day, tzinfo=tz)
        day_end_local = day_start_local + timedelta(days=1)
        work_windows = _parse_hhmm(work_raw)
        free_windows = _subtract(work_windows, _parse_hhmm(breaks_raw))

        booked_minutes: list[tuple[int, int]] = []
        blocking = [a for a in visible if a.status in ("pending", "confirmed")]
        for a in blocking:
            start_local = a.start_at.astimezone(tz)
            end_local = a.end_at.astimezone(tz)
            if end_local <= day_start_local or start_local >= day_end_local:
                continue
            cs = max(start_local, day_start_local)
            ce = min(end_local, day_end_local)
            booked_minutes.append(
                (
                    int((cs - day_start_local).total_seconds() // 60),
                    int((ce - day_start_local).total_seconds() // 60),
                )
            )
        final_free = _subtract(free_windows, booked_minutes)
        for ws, we in final_free:
            cursor = ws
            while cursor + slot_step_min <= we:
                free_slots.append(day_start_local + timedelta(minutes=cursor))
                cursor += slot_step_min

        now_local = now.astimezone(tz)
        if now_local.date() == d:
            free_slots = [s for s in free_slots if s > now_local]

    if work_raw:
        if free_slots:
            lines.append(strings.SCHED_FREE_SECTION)
            lines.append(
                ", ".join(f"{s.hour:02d}:{s.minute:02d}" for s in free_slots)
            )
        else:
            lines.append(strings.SCHED_FREE_NONE)

    text = "\n".join(lines)

    rows: list[list[InlineKeyboardButton]] = _day_nav_rows(day_nav)
    now_utc = now.astimezone(UTC)
    for a in visible:
        if a.status != "confirmed" or a.end_at > now_utc:
            continue
        local = a.start_at.astimezone(tz)
        short = (client_names.get(a.client_id, "—"))[:12]
        rows.append(
            [
                InlineKeyboardButton(
                    text=strings.MARK_PAST_PRESENT.format(
                        time=f"{local.hour:02d}:{local.minute:02d}",
                        short=short,
                    ),
                    callback_data=MarkPastCallback(
                        action="present", appointment_id=a.id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=strings.MARK_PAST_NO_SHOW.format(
                        time=f"{local.hour:02d}:{local.minute:02d}",
                        short=short,
                    ),
                    callback_data=MarkPastCallback(
                        action="no_show", appointment_id=a.id
                    ).pack(),
                ),
            ]
        )

    return text, InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_utils_schedule_format.py -v`
Expected: PASS (5/5)

- [ ] **Step 5: Run full gates**

Run: `ruff check . && ruff format --check . && mypy src/ && pytest -q`

- [ ] **Step 6: Commit**

```bash
git add src/utils/schedule_format.py tests/test_utils_schedule_format.py
git commit -m "feat(utils): pure day-schedule renderer"
```

---

## Task 9: `/today` and `/tomorrow` handlers

**Files:**
- Create: `src/handlers/master/today.py`
- Modify: `src/handlers/master/__init__.py`
- Test: `tests/test_handlers_master_today.py` (new)

Single handler parametrised by offset (0 or 1). Loads master range via `list_for_master_range`, preloads client/service name maps, calls `render_day_schedule`, wires `DayNavCallback` into the keyboard.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handlers_master_today.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.schedule import DayNavCallback
from src.db.models import Appointment, Client, Master, Service
from src.handlers.master.today import cb_day_nav, cmd_today, cmd_tomorrow


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMsg:
    from_user: _FakeUser | None = None
    answers: list[tuple[str, Any]] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.answers.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.answers.append((text, reply_markup))


@dataclass
class _FakeCb:
    from_user: _FakeUser
    message: _FakeMsg = field(default_factory=_FakeMsg)
    answered: list[str] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append(text)


async def _mkctx() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=8001,
        name="M",
        timezone="Asia/Yerevan",
        work_hours={
            "mon": [["10:00", "19:00"]],
            "tue": [["10:00", "19:00"]],
            "wed": [["10:00", "19:00"]],
            "thu": [["10:00", "19:00"]],
            "fri": [["10:00", "19:00"]],
            "sat": [["10:00", "16:00"]],
        },
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499010001")
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add_all([client, svc])
    await session.flush()
    await session.commit()
    return master, client, svc


@pytest.mark.asyncio
async def test_cmd_today_sends_day_schedule(session: AsyncSession) -> None:
    master, *_ = await _seed(session)
    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))

    await cmd_today(message=msg, state=state, session=session, master=master)
    assert msg.answers
    text, kb = msg.answers[0]
    assert "📅" in text
    assert kb is not None


@pytest.mark.asyncio
async def test_cmd_tomorrow_sends_day_schedule(session: AsyncSession) -> None:
    master, *_ = await _seed(session)
    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))

    await cmd_tomorrow(message=msg, state=state, session=session, master=master)
    assert msg.answers


@pytest.mark.asyncio
async def test_cb_day_nav_today_rerenders(session: AsyncSession) -> None:
    master, *_ = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_day_nav(
        callback=cb,  # type: ignore[arg-type]
        callback_data=DayNavCallback(action="today"),
        state=state,
        session=session,
        master=master,
    )
    assert cb.answered


@pytest.mark.asyncio
async def test_mark_past_button_present_for_past_confirmed(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    # Seed a confirmed appointment that ended in the past.
    now = datetime.now(UTC)
    past_start = now - timedelta(hours=3)
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=svc.id,
        start_at=past_start,
        end_at=past_start + timedelta(minutes=60),
        status="confirmed",
        source="master_manual",
        confirmed_at=past_start - timedelta(days=1),
    )
    session.add(appt)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))
    await cmd_today(message=msg, state=state, session=session, master=master)
    _, kb = msg.answers[0]
    packed = [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert any(p.startswith("mpa:") for p in packed)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_master_today.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create the handler**

`src/handlers/master/today.py`:

```python
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.schedule import DayNavCallback
from src.db.models import Client, Master, Service
from src.fsm.master_add import MasterAdd
from src.keyboards.master_add import recent_clients_kb
from src.repositories.appointments import AppointmentRepository
from src.repositories.clients import ClientRepository
from src.strings import strings
from src.utils.schedule_format import render_day_schedule
from src.utils.time import now_utc

router = Router(name="master_today")


def _day_nav(kind: Literal["today", "tomorrow"]) -> list[list[InlineKeyboardButton]]:
    if kind == "today":
        primary = InlineKeyboardButton(
            text=strings.DAY_NAV_TOMORROW,
            callback_data=DayNavCallback(action="tomorrow").pack(),
        )
    else:
        primary = InlineKeyboardButton(
            text=strings.DAY_NAV_TODAY,
            callback_data=DayNavCallback(action="today").pack(),
        )
    return [
        [
            primary,
            InlineKeyboardButton(
                text=strings.DAY_NAV_WEEK,
                callback_data=DayNavCallback(action="week").pack(),
            ),
            InlineKeyboardButton(
                text=strings.DAY_NAV_ADD,
                callback_data=DayNavCallback(action="add").pack(),
            ),
        ]
    ]


async def _render_for(
    *,
    session: AsyncSession,
    master: Master,
    offset_days: int,
) -> tuple[str, object]:
    tz = ZoneInfo(master.timezone)
    today_local = now_utc().astimezone(tz).date()
    d = today_local + timedelta(days=offset_days)

    day_start_utc = datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(UTC)
    day_end_utc = day_start_utc + timedelta(days=1)
    repo = AppointmentRepository(session)
    appts = await repo.list_for_master_range(
        master.id,
        start_utc=day_start_utc,
        end_utc=day_end_utc,
        statuses=("pending", "confirmed", "completed", "no_show"),
    )

    client_ids = {a.client_id for a in appts}
    service_ids = {a.service_id for a in appts}
    client_names: dict[UUID, str] = {}
    service_names: dict[UUID, str] = {}
    if client_ids:
        rows = await session.scalars(select(Client).where(Client.id.in_(client_ids)))
        for c in rows.all():
            client_names[c.id] = c.name
    if service_ids:
        rows = await session.scalars(select(Service).where(Service.id.in_(service_ids)))
        for s in rows.all():
            service_names[s.id] = s.name

    kind: Literal["today", "tomorrow"] = "today" if offset_days == 0 else "tomorrow"
    return render_day_schedule(
        d=d,
        appts=appts,
        client_names=client_names,
        service_names=service_names,
        work_hours=master.work_hours,
        breaks=master.breaks,
        tz=tz,
        slot_step_min=master.slot_step_min,
        now=now_utc(),
        day_nav=_day_nav(kind),
    )


@router.message(Command("today"))
async def cmd_today(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await state.clear()
    text, kb = await _render_for(session=session, master=master, offset_days=0)
    await message.answer(text, reply_markup=kb)


@router.message(Command("tomorrow"))
async def cmd_tomorrow(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await state.clear()
    text, kb = await _render_for(session=session, master=master, offset_days=1)
    await message.answer(text, reply_markup=kb)


@router.callback_query(DayNavCallback.filter())
async def cb_day_nav(
    callback: CallbackQuery,
    callback_data: DayNavCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    action = callback_data.action
    if action == "today":
        text, kb = await _render_for(session=session, master=master, offset_days=0)
        if callback.message is not None and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(text, reply_markup=kb)
        return
    if action == "tomorrow":
        text, kb = await _render_for(session=session, master=master, offset_days=1)
        if callback.message is not None and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(text, reply_markup=kb)
        return
    if action == "week":
        from src.handlers.master.week import render_week  # local import avoids cycle

        text, kb = await render_week(session=session, master=master)
        if callback.message is not None and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(text, reply_markup=kb)
        return
    if action == "calendar":
        from src.handlers.master.calendar import render_calendar

        text, kb = await render_calendar(session=session, master=master, month=None)
        if callback.message is not None and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(text, reply_markup=kb)
        return
    if action == "add":
        await state.clear()
        await state.set_state(MasterAdd.PickingClient)
        repo = ClientRepository(session)
        clients = await repo.list_recent_by_master(master.id)
        text_prompt = strings.MANUAL_PICK_CLIENT if clients else strings.MANUAL_NO_RECENT
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(
                text_prompt, reply_markup=recent_clients_kb(clients)
            )
        return
```

Note the local imports of `render_week` and `render_calendar` — those are implemented in Tasks 11 and 12 as module-level `async def` helpers and are referenced here to avoid cycles. For now, tests for `week` and `calendar` navigation actions are out of scope of this task's tests (they are covered in their respective tasks).

- [ ] **Step 4: Register the router**

Modify `src/handlers/master/__init__.py`. Add import and include:

```python
from src.handlers.master.today import router as today_router
...
router.include_router(today_router)
```

(Place after `add_manual_router`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_handlers_master_today.py -v`
Expected: PASS (4/4). The `week`/`calendar` branches of `cb_day_nav` will `ImportError` only if exercised — they aren't in these tests.

- [ ] **Step 6: Run full gates**

Run: `ruff check . && ruff format --check . && mypy src/ && pytest -q`

> mypy note: the local imports use `render_week` / `render_calendar` symbols that don't exist yet. Add TYPE_CHECKING imports OR temporarily comment out those two branches. **Recommended:** comment out the two `if action == "week"` and `if action == "calendar"` blocks for now and re-enable them in Tasks 11 and 12. Leave an explicit `# Epic 6: re-enabled in Task 11` marker so the engineer doesn't forget.

Re-run gates.

- [ ] **Step 7: Commit**

```bash
git add src/handlers/master/today.py src/handlers/master/__init__.py tests/test_handlers_master_today.py
git commit -m "feat(handler): /today and /tomorrow with day-nav callbacks"
```

---

## Task 10: Mark-past handler

**Files:**
- Create: `src/handlers/master/mark_past.py`
- Modify: `src/handlers/master/__init__.py`
- Test: `tests/test_handlers_master_mark_past.py` (new)

Callback → service call → edit message in place. "message is not modified" is swallowed; other telegram errors are logged but don't propagate.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handlers_master_mark_past.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.mark_past import MarkPastCallback
from src.db.models import Appointment, Client, Master, Service
from src.handlers.master.mark_past import cb_mark_past


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMsg:
    from_user: _FakeUser | None = None
    edits: list[tuple[str, Any]] = field(default_factory=list)

    async def edit_text(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.edits.append((text, reply_markup))


@dataclass
class _FakeCb:
    from_user: _FakeUser
    message: _FakeMsg = field(default_factory=_FakeMsg)
    answered: list[tuple[str, bool]] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append((text, show_alert))


async def _mkctx() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed_past_confirmed(
    session: AsyncSession,
) -> tuple[Master, Appointment]:
    master = Master(
        tg_id=8101,
        name="M",
        timezone="Asia/Yerevan",
        work_hours={"mon": [["10:00", "19:00"]], "tue": [["10:00", "19:00"]]},
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499020001")
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add_all([client, svc])
    await session.flush()

    start = datetime.now(UTC) - timedelta(hours=3)
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=svc.id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status="confirmed",
        source="master_manual",
        confirmed_at=start - timedelta(days=1),
    )
    session.add(appt)
    await session.flush()
    await session.commit()
    return master, appt


@pytest.mark.asyncio
async def test_cb_mark_past_present_transitions_to_completed(session: AsyncSession) -> None:
    master, appt = await _seed_past_confirmed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_mark_past(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MarkPastCallback(action="present", appointment_id=appt.id),
        state=state,
        session=session,
        master=master,
    )
    await session.refresh(appt)
    assert appt.status == "completed"
    assert cb.answered


@pytest.mark.asyncio
async def test_cb_mark_past_no_show_transitions(session: AsyncSession) -> None:
    master, appt = await _seed_past_confirmed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_mark_past(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MarkPastCallback(action="no_show", appointment_id=appt.id),
        state=state,
        session=session,
        master=master,
    )
    await session.refresh(appt)
    assert appt.status == "no_show"


@pytest.mark.asyncio
async def test_cb_mark_past_unknown_shows_alert(session: AsyncSession) -> None:
    master = Master(tg_id=8102, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_mark_past(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MarkPastCallback(action="present", appointment_id=uuid4()),
        state=state,
        session=session,
        master=master,
    )
    # The alert text is one of the MARK_PAST_NOT_AVAILABLE / NOT_ENDED / ALREADY_CLOSED.
    assert cb.answered
    assert cb.answered[0][1] is True  # show_alert
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_master_mark_past.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create the handler**

`src/handlers/master/mark_past.py`:

```python
from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.mark_past import MarkPastCallback
from src.db.models import Master
from src.exceptions import InvalidState, NotFound
from src.handlers.master.today import _render_for
from src.services.booking import BookingService
from src.strings import strings
from src.utils.time import now_utc

router = Router(name="master_mark_past")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


@router.callback_query(MarkPastCallback.filter())
async def cb_mark_past(
    callback: CallbackQuery,
    callback_data: MarkPastCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    svc = BookingService(session)
    try:
        if callback_data.action == "present":
            await svc.mark_completed(callback_data.appointment_id, master=master)
            await callback.answer(strings.MARK_PAST_OK_COMPLETED)
        else:
            await svc.mark_no_show(callback_data.appointment_id, master=master)
            await callback.answer(strings.MARK_PAST_OK_NO_SHOW)
    except NotFound:
        await callback.answer(strings.MARK_PAST_NOT_AVAILABLE, show_alert=True)
        return
    except InvalidState as exc:
        msg = (
            strings.MARK_PAST_NOT_ENDED
            if "not ended" in str(exc)
            else strings.MARK_PAST_ALREADY_CLOSED
        )
        await callback.answer(msg, show_alert=True)
        return

    # Re-render the day in place. We don't know which day the keyboard is for —
    # the appointment's start_at (local tz) is authoritative; simplest path is to
    # recompute "today" offset so the user sees the updated schedule.
    text, kb = await _render_for(session=session, master=master, offset_days=0)
    if callback.message is None or not hasattr(callback.message, "edit_text"):
        return
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        log.warning("mark_past edit failed", err=str(exc))
```

- [ ] **Step 4: Register the router**

Modify `src/handlers/master/__init__.py` — add `from src.handlers.master.mark_past import router as mark_past_router` and `router.include_router(mark_past_router)` after `today_router`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_handlers_master_mark_past.py -v`
Expected: PASS (3/3). The edit-in-place path silently noops when `message.edit_text` doesn't exist (the `_FakeMsg` in tests provides it).

- [ ] **Step 6: Run full gates**

Run: `ruff check . && ruff format --check . && mypy src/ && pytest -q`

- [ ] **Step 7: Commit**

```bash
git add src/handlers/master/mark_past.py src/handlers/master/__init__.py tests/test_handlers_master_mark_past.py
git commit -m "feat(handler): mark-past (✅ был / ❌ не пришёл) for confirmed"
```

---

## Task 11: `/week` handler

**Files:**
- Create: `src/handlers/master/week.py`
- Modify: `src/handlers/master/__init__.py`
- Modify: `src/handlers/master/today.py` (re-enable the `week` branch)
- Test: `tests/test_handlers_master_week.py` (new)

7-day snapshot, grouped by local date. Bar is 8 chars from `booked_min / work_min`. Day buttons use `DayPickCallback`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handlers_master_week.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.schedule import DayPickCallback
from src.db.models import Appointment, Client, Master, Service
from src.handlers.master.week import cb_day_pick, cmd_week, render_week


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
class _FakeCb:
    from_user: _FakeUser
    message: _FakeMsg = field(default_factory=_FakeMsg)
    answered: list[str] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append(text)


async def _mkctx() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed(session: AsyncSession) -> Master:
    master = Master(
        tg_id=8201,
        name="M",
        timezone="Asia/Yerevan",
        work_hours={
            "mon": [["10:00", "19:00"]],
            "tue": [["10:00", "19:00"]],
            "wed": [["10:00", "19:00"]],
            "thu": [["10:00", "19:00"]],
            "fri": [["10:00", "19:00"]],
            "sat": [["10:00", "16:00"]],
        },
    )
    session.add(master)
    await session.flush()
    await session.commit()
    return master


@pytest.mark.asyncio
async def test_cmd_week_sends_snapshot(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))
    await cmd_week(message=msg, state=state, session=session, master=master)
    assert msg.answers
    text, kb = msg.answers[0]
    assert "🗓" in text
    # 7 day buttons + bottom row (today + calendar) minimum.
    packed = [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    dpk = [p for p in packed if p.startswith("dpk:")]
    assert len(dpk) == 7


@pytest.mark.asyncio
async def test_render_week_reflects_load(session: AsyncSession) -> None:
    master = await _seed(session)
    # Insert an appointment 2 days from now at 11 local — should push "count" to 1.
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Asia/Yerevan")
    tomorrow = (datetime.now(UTC).astimezone(tz) + timedelta(days=1)).date()
    start_local = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 11, tzinfo=tz)
    start = start_local.astimezone(UTC)
    client = Client(master_id=master.id, name="C", phone="+37499030001")
    svc = Service(master_id=master.id, name="S", duration_min=60)
    session.add_all([client, svc])
    await session.flush()
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=svc.id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status="confirmed",
        source="master_manual",
    )
    session.add(appt)
    await session.flush()
    await session.commit()

    text, _ = await render_week(session=session, master=master)
    assert "1 зап" in text


@pytest.mark.asyncio
async def test_cb_day_pick_sends_day_schedule(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_day_pick(
        callback=cb,  # type: ignore[arg-type]
        callback_data=DayPickCallback(ymd="2026-04-24"),
        state=state,
        session=session,
        master=master,
    )
    assert cb.message.answers
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_master_week.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create the handler**

`src/handlers/master/week.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.schedule import DayNavCallback, DayPickCallback
from src.db.models import Client, Master, Service
from src.repositories.appointments import AppointmentRepository
from src.services.availability import WEEKDAYS
from src.strings import strings
from src.utils.schedule_format import render_day_schedule
from src.utils.time import now_utc

router = Router(name="master_week")


def _parse_hhmm(raw: list[list[str]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in raw:
        sh, sm = s.split(":")
        eh, em = e.split(":")
        out.append((int(sh) * 60 + int(sm), int(eh) * 60 + int(em)))
    return out


def _work_minutes(work_hours: dict, breaks: dict, weekday_key: str) -> int:
    raw = work_hours.get(weekday_key) or []
    if not raw:
        return 0
    total = sum(e - s for s, e in _parse_hhmm(raw))
    br = breaks.get(weekday_key) or []
    total -= sum(e - s for s, e in _parse_hhmm(br))
    return max(0, total)


def _bar(filled: int, total: int = 8) -> str:
    filled = max(0, min(total, filled))
    return "▰" * filled + "▱" * (total - filled)


@dataclass(frozen=True)
class _DaySummary:
    d: date
    count: int
    booked_min: int
    work_min: int


async def _collect_week(
    *, session: AsyncSession, master: Master
) -> tuple[list[_DaySummary], ZoneInfo, date]:
    tz = ZoneInfo(master.timezone)
    today_local = now_utc().astimezone(tz).date()
    start = datetime(today_local.year, today_local.month, today_local.day, tzinfo=tz)
    end = start + timedelta(days=7)
    repo = AppointmentRepository(session)
    appts = await repo.list_for_master_range(
        master.id,
        start_utc=start.astimezone(UTC),
        end_utc=end.astimezone(UTC),
    )

    by_day: dict[date, list[tuple[int]]] = {}
    for a in appts:
        local = a.start_at.astimezone(tz).date()
        by_day.setdefault(local, [])
        by_day[local].append(
            (int((a.end_at - a.start_at).total_seconds() // 60),)
        )

    summaries: list[_DaySummary] = []
    for offset in range(7):
        d = today_local + timedelta(days=offset)
        rows = by_day.get(d, [])
        weekday_key = WEEKDAYS[d.weekday()]
        summaries.append(
            _DaySummary(
                d=d,
                count=len(rows),
                booked_min=sum(r[0] for r in rows),
                work_min=_work_minutes(master.work_hours, master.breaks, weekday_key),
            )
        )
    return summaries, tz, today_local


def _week_keyboard(summaries: list[_DaySummary]) -> InlineKeyboardMarkup:
    day_buttons: list[InlineKeyboardButton] = [
        InlineKeyboardButton(
            text=strings.WEEK_BTN_DAY.format(
                wd=strings.WEEKDAY_SHORT[s.d.weekday()],
                dd=f"{s.d.day:02d}",
            ),
            callback_data=DayPickCallback(ymd=s.d.isoformat()).pack(),
        )
        for s in summaries
    ]
    rows: list[list[InlineKeyboardButton]] = [
        day_buttons[0:3],
        day_buttons[3:6],
        day_buttons[6:7],
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.DAY_NAV_TODAY,
                callback_data=DayNavCallback(action="today").pack(),
            ),
            InlineKeyboardButton(
                text=strings.DAY_NAV_CALENDAR,
                callback_data=DayNavCallback(action="calendar").pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_week(
    *, session: AsyncSession, master: Master
) -> tuple[str, InlineKeyboardMarkup]:
    summaries, _, today_local = await _collect_week(session=session, master=master)
    month_short = str(strings.MONTH_NAMES[today_local.month - 1])[:3].lower()
    lines = [
        strings.WEEK_HEADER.format(dd=f"{today_local.day:02d}", mon=month_short),
        "",
    ]
    for s in summaries:
        wd = str(strings.WEEKDAY_SHORT[s.d.weekday()])
        if s.work_min <= 0:
            lines.append(
                strings.WEEK_DAY_LINE_OFF.format(
                    wd=wd,
                    dd=f"{s.d.day:02d}",
                    mm=f"{s.d.month:02d}",
                    bar=_bar(0),
                )
            )
            continue
        ratio = s.booked_min / s.work_min
        filled = round(ratio * 8)
        pct = round(ratio * 100)
        lines.append(
            strings.WEEK_DAY_LINE.format(
                wd=wd,
                dd=f"{s.d.day:02d}",
                mm=f"{s.d.month:02d}",
                count=s.count,
                bar=_bar(filled),
                pct=pct,
            )
        )
    return "\n".join(lines), _week_keyboard(summaries)


@router.message(Command("week"))
async def cmd_week(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await state.clear()
    text, kb = await render_week(session=session, master=master)
    await message.answer(text, reply_markup=kb)


@router.callback_query(DayPickCallback.filter())
async def cb_day_pick(
    callback: CallbackQuery,
    callback_data: DayPickCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    picked = date.fromisoformat(callback_data.ymd)

    tz = ZoneInfo(master.timezone)
    day_start_utc = datetime(picked.year, picked.month, picked.day, tzinfo=tz).astimezone(UTC)
    day_end_utc = day_start_utc + timedelta(days=1)
    repo = AppointmentRepository(session)
    appts = await repo.list_for_master_range(
        master.id,
        start_utc=day_start_utc,
        end_utc=day_end_utc,
        statuses=("pending", "confirmed", "completed", "no_show"),
    )

    client_ids = {a.client_id for a in appts}
    service_ids = {a.service_id for a in appts}
    client_names: dict[UUID, str] = {}
    service_names: dict[UUID, str] = {}
    if client_ids:
        rows = await session.scalars(select(Client).where(Client.id.in_(client_ids)))
        for c in rows.all():
            client_names[c.id] = c.name
    if service_ids:
        rows = await session.scalars(select(Service).where(Service.id.in_(service_ids)))
        for s in rows.all():
            service_names[s.id] = s.name

    day_nav = [
        [
            InlineKeyboardButton(
                text=strings.DAY_NAV_BACK_TO_WEEK,
                callback_data=DayNavCallback(action="week").pack(),
            ),
            InlineKeyboardButton(
                text=strings.DAY_NAV_CALENDAR,
                callback_data=DayNavCallback(action="calendar").pack(),
            ),
        ]
    ]
    text, kb = render_day_schedule(
        d=picked,
        appts=appts,
        client_names=client_names,
        service_names=service_names,
        work_hours=master.work_hours,
        breaks=master.breaks,
        tz=tz,
        slot_step_min=master.slot_step_min,
        now=now_utc(),
        day_nav=day_nav,
    )
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(text, reply_markup=kb)
```

- [ ] **Step 4: Re-enable the `week` branch in `today.py`**

Uncomment (or add back) the `if action == "week"` branch in `src/handlers/master/today.py::cb_day_nav`. The local import `from src.handlers.master.week import render_week` now resolves.

- [ ] **Step 5: Register the router**

Modify `src/handlers/master/__init__.py` — add `from src.handlers.master.week import router as week_router` and `router.include_router(week_router)` after `mark_past_router`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_handlers_master_week.py tests/test_handlers_master_today.py -v`
Expected: PASS on both suites.

- [ ] **Step 7: Run full gates**

Run: `ruff check . && ruff format --check . && mypy src/ && pytest -q`

- [ ] **Step 8: Commit**

```bash
git add src/handlers/master/week.py src/handlers/master/today.py src/handlers/master/__init__.py tests/test_handlers_master_week.py
git commit -m "feat(handler): /week with 7-day load snapshot + day-pick"
```

---

## Task 12: `/calendar` handler

**Files:**
- Create: `src/handlers/master/calendar.py`
- Modify: `src/handlers/master/__init__.py`
- Modify: `src/handlers/master/today.py` (re-enable the `calendar` branch)
- Test: `tests/test_handlers_master_calendar.py` (new)

Master calendar uses its own callback class (`MasterCalendarCallback`, prefix `mca`) to stay out of the client booking flow. Rendering re-uses `calendar_keyboard` with `allow_past=True` and an adapter that re-packages the rendered `CalendarCallback` buttons into `MasterCalendarCallback` payloads.

Because `calendar_keyboard` internally emits `CalendarCallback` payloads, we replicate the month grid here with the master prefix rather than rewriting the shared keyboard. This keeps the client path untouched.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handlers_master_calendar.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.master_calendar import MasterCalendarCallback
from src.db.models import Master
from src.handlers.master.calendar import cb_master_calendar, cmd_calendar, render_calendar


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMsg:
    from_user: _FakeUser | None = None
    answers: list[tuple[str, Any]] = field(default_factory=list)
    edits: list[tuple[str, Any]] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.answers.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.edits.append((text, reply_markup))


@dataclass
class _FakeCb:
    from_user: _FakeUser
    message: _FakeMsg = field(default_factory=_FakeMsg)
    answered: list[str] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append(text)


async def _mkctx() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed(session: AsyncSession) -> Master:
    master = Master(
        tg_id=8301,
        name="M",
        timezone="Asia/Yerevan",
        work_hours={"mon": [["10:00", "19:00"]]},
    )
    session.add(master)
    await session.flush()
    await session.commit()
    return master


@pytest.mark.asyncio
async def test_cmd_calendar_renders_current_month(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))
    await cmd_calendar(message=msg, state=state, session=session, master=master)
    assert msg.answers


@pytest.mark.asyncio
async def test_cb_master_calendar_nav_to_prior_month(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_master_calendar(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MasterCalendarCallback(action="nav", year=2026, month=3, day=0),
        state=state,
        session=session,
        master=master,
    )
    # Nav edits the existing message.
    assert cb.message.edits


@pytest.mark.asyncio
async def test_cb_master_calendar_pick_sends_day(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_master_calendar(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MasterCalendarCallback(action="pick", year=2026, month=4, day=20),
        state=state,
        session=session,
        master=master,
    )
    assert cb.message.answers


@pytest.mark.asyncio
async def test_cb_master_calendar_noop_just_answers(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_master_calendar(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MasterCalendarCallback(action="noop", year=2026, month=4, day=0),
        state=state,
        session=session,
        master=master,
    )
    assert cb.answered


@pytest.mark.asyncio
async def test_render_calendar_current_month_default(session: AsyncSession) -> None:
    master = await _seed(session)
    text, kb = await render_calendar(session=session, master=master, month=None)
    assert text
    assert kb is not None


@pytest.mark.asyncio
async def test_render_calendar_past_month(session: AsyncSession) -> None:
    master = await _seed(session)
    text, kb = await render_calendar(
        session=session, master=master, month=date(2025, 1, 1)
    )
    assert text
    # Past-month cells should include 'pick' actions (allow_past=True).
    packed = [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if btn.callback_data
    ]
    assert any(p.startswith("mca:pick") for p in packed)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_master_calendar.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create the handler**

`src/handlers/master/calendar.py`:

```python
from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.master_calendar import MasterCalendarCallback
from src.callback_data.schedule import DayNavCallback
from src.db.models import Client, Master, Service
from src.repositories.appointments import AppointmentRepository
from src.services.availability import WEEKDAYS
from src.strings import strings
from src.utils.schedule_format import render_day_schedule
from src.utils.time import now_utc

router = Router(name="master_calendar")


def _noop_btn(text: str, year: int, month: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=MasterCalendarCallback(
            action="noop", year=year, month=month, day=0
        ).pack(),
    )


def _shift_month(d: date, by: int) -> date:
    total = d.year * 12 + (d.month - 1) + by
    return date(total // 12, (total % 12) + 1, 1)


async def _month_load(
    *, session: AsyncSession, master: Master, month: date
) -> dict[date, int]:
    """Return per-day appointment count for the month (negative for days off)."""
    tz = ZoneInfo(master.timezone)
    first = datetime(month.year, month.month, 1, tzinfo=tz)
    last = _shift_month(month, +1)
    last_dt = datetime(last.year, last.month, 1, tzinfo=tz)
    repo = AppointmentRepository(session)
    appts = await repo.list_for_master_range(
        master.id,
        start_utc=first.astimezone(UTC),
        end_utc=last_dt.astimezone(UTC),
        statuses=("pending", "confirmed", "completed", "no_show"),
    )

    _, days_in_month = monthrange(month.year, month.month)
    counts: dict[date, int] = {}
    for day_num in range(1, days_in_month + 1):
        d = date(month.year, month.month, day_num)
        wk = WEEKDAYS[d.weekday()]
        counts[d] = -1 if not master.work_hours.get(wk) else 0
    for a in appts:
        local_day = a.start_at.astimezone(tz).date()
        if counts.get(local_day, -1) >= 0:
            counts[local_day] += 1
    return counts


def _month_keyboard(
    *, month: date, counts: dict[date, int], today: date
) -> InlineKeyboardMarkup:
    year, month_num = month.year, month.month
    month_name = str(strings.MONTH_NAMES[month_num - 1])

    prev_shift = _shift_month(month, -1)
    next_shift = _shift_month(month, +1)
    header = [
        InlineKeyboardButton(
            text="«",
            callback_data=MasterCalendarCallback(
                action="nav", year=prev_shift.year, month=prev_shift.month, day=0
            ).pack(),
        ),
        _noop_btn(f"{month_name} {year}", year, month_num),
        InlineKeyboardButton(
            text="»",
            callback_data=MasterCalendarCallback(
                action="nav", year=next_shift.year, month=next_shift.month, day=0
            ).pack(),
        ),
    ]
    weekday_row = [_noop_btn(lbl, year, month_num) for lbl in strings.WEEKDAY_SHORT]
    rows: list[list[InlineKeyboardButton]] = [header, weekday_row]

    _, days_in_month = monthrange(year, month_num)
    first_weekday = date(year, month_num, 1).weekday()

    cells: list[InlineKeyboardButton] = [
        _noop_btn(" ", year, month_num) for _ in range(first_weekday)
    ]
    for day in range(1, days_in_month + 1):
        d = date(year, month_num, day)
        count = counts.get(d, -1)
        if count < 0:
            emoji = "⚫"
        elif count == 0:
            emoji = "🟢"
        elif count < 5:
            emoji = "🟡"
        else:
            emoji = "🔴"
        label = f"{emoji}{day}"
        if count < 0:
            cells.append(_noop_btn(label, year, month_num))
        else:
            cells.append(
                InlineKeyboardButton(
                    text=label,
                    callback_data=MasterCalendarCallback(
                        action="pick", year=year, month=month_num, day=day
                    ).pack(),
                )
            )
    while len(cells) % 7 != 0:
        cells.append(_noop_btn(" ", year, month_num))
    for i in range(0, len(cells), 7):
        rows.append(cells[i : i + 7])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_calendar(
    *, session: AsyncSession, master: Master, month: date | None
) -> tuple[str, InlineKeyboardMarkup]:
    tz = ZoneInfo(master.timezone)
    today_local = now_utc().astimezone(tz).date()
    effective_month = month or today_local.replace(day=1)
    counts = await _month_load(session=session, master=master, month=effective_month)
    kb = _month_keyboard(month=effective_month, counts=counts, today=today_local)
    header_name = str(strings.MONTH_NAMES[effective_month.month - 1])
    text = f"🗓 {header_name} {effective_month.year}"
    return text, kb


@router.message(Command("calendar"))
async def cmd_calendar(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await state.clear()
    text, kb = await render_calendar(session=session, master=master, month=None)
    await message.answer(text, reply_markup=kb)


async def _render_day(
    *, session: AsyncSession, master: Master, d: date
) -> tuple[str, InlineKeyboardMarkup]:
    tz = ZoneInfo(master.timezone)
    day_start_utc = datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(UTC)
    day_end_utc = day_start_utc + timedelta(days=1)
    repo = AppointmentRepository(session)
    appts = await repo.list_for_master_range(
        master.id,
        start_utc=day_start_utc,
        end_utc=day_end_utc,
        statuses=("pending", "confirmed", "completed", "no_show"),
    )
    client_ids = {a.client_id for a in appts}
    service_ids = {a.service_id for a in appts}
    client_names: dict[UUID, str] = {}
    service_names: dict[UUID, str] = {}
    if client_ids:
        rows = await session.scalars(select(Client).where(Client.id.in_(client_ids)))
        for c in rows.all():
            client_names[c.id] = c.name
    if service_ids:
        rows = await session.scalars(select(Service).where(Service.id.in_(service_ids)))
        for s in rows.all():
            service_names[s.id] = s.name

    day_nav = [
        [
            InlineKeyboardButton(
                text=strings.DAY_NAV_BACK_TO_CALENDAR,
                callback_data=DayNavCallback(action="calendar").pack(),
            )
        ]
    ]
    return render_day_schedule(
        d=d,
        appts=appts,
        client_names=client_names,
        service_names=service_names,
        work_hours=master.work_hours,
        breaks=master.breaks,
        tz=tz,
        slot_step_min=master.slot_step_min,
        now=now_utc(),
        day_nav=day_nav,
    )


@router.callback_query(MasterCalendarCallback.filter())
async def cb_master_calendar(
    callback: CallbackQuery,
    callback_data: MasterCalendarCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    if callback_data.action == "noop":
        return
    if callback_data.action == "nav":
        month = date(callback_data.year, callback_data.month, 1)
        text, kb = await render_calendar(session=session, master=master, month=month)
        if callback.message is not None and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(text, reply_markup=kb)
        return
    # pick
    d = date(callback_data.year, callback_data.month, callback_data.day)
    text, kb = await _render_day(session=session, master=master, d=d)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(text, reply_markup=kb)
```

- [ ] **Step 4: Re-enable the `calendar` branch in `today.py`**

Uncomment (or add back) the `if action == "calendar"` branch in `src/handlers/master/today.py::cb_day_nav`.

- [ ] **Step 5: Register the router**

Modify `src/handlers/master/__init__.py` — add `from src.handlers.master.calendar import router as calendar_router` and `router.include_router(calendar_router)` after `week_router`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_handlers_master_calendar.py tests/test_handlers_master_today.py tests/test_handlers_master_week.py -v`

- [ ] **Step 7: Run full gates**

Run: `ruff check . && ruff format --check . && mypy src/ && pytest -q`

- [ ] **Step 8: Commit**

```bash
git add src/handlers/master/calendar.py src/handlers/master/today.py src/handlers/master/__init__.py tests/test_handlers_master_calendar.py
git commit -m "feat(handler): /calendar with arbitrary-month nav and day drill-down"
```

---

## Task 13: `/client` handler (search + page + notes + bridge)

**Files:**
- Create: `src/handlers/master/client_page.py`
- Modify: `src/handlers/master/__init__.py`
- Test: `tests/test_handlers_master_client_page.py` (new)

This is the largest handler — five entry points:
1. `/client` command → `MasterView.SearchingClient`, prompt.
2. Text while in `SearchingClient` → search, show 0/1/many result.
3. `ClientPickCallback` → open client page, clear state.
4. `ClientNotesEditCallback` → `MasterView.EditingNotes`, prompt.
5. Text while in `EditingNotes` → save (or clear on `-`), re-render page, clear state.
6. `ClientAddApptCallback` → set `MasterAdd.PickingService` with `client_id` pre-loaded, show services picker.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_handlers_master_client_page.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.client_page import (
    ClientAddApptCallback,
    ClientNotesEditCallback,
    ClientPickCallback,
)
from src.db.models import Appointment, Client, Master, Service
from src.fsm.master_add import MasterAdd
from src.fsm.master_view import MasterView
from src.handlers.master.client_page import (
    cb_add_appt,
    cb_edit_notes,
    cb_pick_client,
    cmd_client,
    msg_notes_edit,
    msg_search_query,
)


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMsg:
    from_user: _FakeUser | None = None
    text: str | None = None
    answers: list[tuple[str, Any]] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.answers.append((text, reply_markup))


@dataclass
class _FakeCb:
    from_user: _FakeUser
    message: _FakeMsg = field(default_factory=_FakeMsg)
    answered: list[str] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append(text)


async def _mkctx() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(tg_id=8401, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499040001")
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add_all([client, svc])
    await session.flush()
    await session.commit()
    return master, client, svc


@pytest.mark.asyncio
async def test_cmd_client_enters_search_state(session: AsyncSession) -> None:
    master, *_ = await _seed(session)
    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))
    await cmd_client(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterView.SearchingClient.state
    assert msg.answers


@pytest.mark.asyncio
async def test_msg_search_too_short_stays(session: AsyncSession) -> None:
    master, *_ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterView.SearchingClient)
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="a")
    await msg_search_query(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterView.SearchingClient.state


@pytest.mark.asyncio
async def test_msg_search_one_result_opens_page(session: AsyncSession) -> None:
    master, client, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterView.SearchingClient)
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="Анн")
    await msg_search_query(message=msg, state=state, session=session, master=master)
    # State cleared after page open.
    assert await state.get_state() is None
    assert msg.answers


@pytest.mark.asyncio
async def test_msg_search_many_results_shows_picker(session: AsyncSession) -> None:
    master, client_a, _ = await _seed(session)
    client_b = Client(master_id=master.id, name="Анастасия", phone="+37499040002")
    session.add(client_b)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterView.SearchingClient)
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="Ан")
    await msg_search_query(message=msg, state=state, session=session, master=master)
    # Still in search state; picker shown.
    assert await state.get_state() == MasterView.SearchingClient.state


@pytest.mark.asyncio
async def test_msg_search_empty_results_reprompts(session: AsyncSession) -> None:
    master, *_ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterView.SearchingClient)
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="Zzyzx")
    await msg_search_query(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterView.SearchingClient.state


@pytest.mark.asyncio
async def test_cb_pick_client_opens_page(session: AsyncSession) -> None:
    master, client, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterView.SearchingClient)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_pick_client(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientPickCallback(client_id=client.id),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() is None
    assert cb.message.answers


@pytest.mark.asyncio
async def test_cb_pick_unknown_client_answers_not_found(session: AsyncSession) -> None:
    master, *_ = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_pick_client(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientPickCallback(client_id=uuid4()),
        state=state,
        session=session,
        master=master,
    )
    assert cb.answered


@pytest.mark.asyncio
async def test_cb_edit_notes_enters_editing_state(session: AsyncSession) -> None:
    master, client, _ = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_edit_notes(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientNotesEditCallback(client_id=client.id),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterView.EditingNotes.state
    data = await state.get_data()
    assert data.get("client_id") == str(client.id)


@pytest.mark.asyncio
async def test_msg_notes_edit_saves_value(session: AsyncSession) -> None:
    master, client, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterView.EditingNotes)
    await state.update_data(client_id=str(client.id))
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="ВИП клиент")
    await msg_notes_edit(message=msg, state=state, session=session, master=master)
    await session.refresh(client)
    assert client.notes == "ВИП клиент"
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_msg_notes_edit_dash_clears_value(session: AsyncSession) -> None:
    master, client, _ = await _seed(session)
    client.notes = "old"
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterView.EditingNotes)
    await state.update_data(client_id=str(client.id))
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="-")
    await msg_notes_edit(message=msg, state=state, session=session, master=master)
    await session.refresh(client)
    assert client.notes is None


@pytest.mark.asyncio
async def test_msg_notes_edit_caps_at_500_chars(session: AsyncSession) -> None:
    master, client, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterView.EditingNotes)
    await state.update_data(client_id=str(client.id))
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="x" * 1000)
    await msg_notes_edit(message=msg, state=state, session=session, master=master)
    await session.refresh(client)
    assert client.notes is not None
    assert len(client.notes) == 500


@pytest.mark.asyncio
async def test_cb_add_appt_bridges_to_picking_service(session: AsyncSession) -> None:
    master, client, _ = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_add_appt(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientAddApptCallback(client_id=client.id),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.PickingService.state
    data = await state.get_data()
    assert data.get("client_id") == str(client.id)


@pytest.mark.asyncio
async def test_client_page_includes_recent_history(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    # Seed a handful of historical appointments.
    now = datetime.now(UTC)
    for i, status in enumerate(["completed", "confirmed", "cancelled", "no_show"]):
        session.add(
            Appointment(
                master_id=master.id,
                client_id=client.id,
                service_id=svc.id,
                start_at=now - timedelta(days=i + 1),
                end_at=now - timedelta(days=i + 1) + timedelta(minutes=60),
                status=status,
                source="master_manual",
                confirmed_at=now - timedelta(days=i + 2),
            )
        )
    await session.flush()
    await session.commit()

    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_pick_client(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientPickCallback(client_id=client.id),
        state=state,
        session=session,
        master=master,
    )
    text, _ = cb.message.answers[0]
    assert "История" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers_master_client_page.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create the handler**

`src/handlers/master/client_page.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.client_page import (
    ClientAddApptCallback,
    ClientNotesEditCallback,
    ClientPickCallback,
)
from src.db.models import Appointment, Client, Master, Service
from src.fsm.master_add import MasterAdd
from src.fsm.master_view import MasterView
from src.keyboards.slots import services_pick_kb
from src.repositories.clients import ClientRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.strings import strings
from src.utils.time import now_utc

router = Router(name="master_client_page")

_MIN_SEARCH = 2
_NOTES_MAX = 500
_HISTORY_LIMIT = 20


def _search_results_kb(clients: list[Client]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{c.name} · {c.phone}",
                callback_data=ClientPickCallback(client_id=c.id).pack(),
            )
        ]
        for c in clients
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _client_page_kb(client_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.CLIENT_PAGE_BTN_EDIT_NOTES,
                    callback_data=ClientNotesEditCallback(client_id=client_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.CLIENT_PAGE_BTN_ADD_APPT,
                    callback_data=ClientAddApptCallback(client_id=client_id).pack(),
                )
            ],
        ]
    )


def _history_suffix(a: Appointment, now: datetime) -> str:
    if a.status == "cancelled":
        return strings.CLIENT_PAGE_SUFFIX_CANCELLED
    if a.status == "rejected":
        return strings.CLIENT_PAGE_SUFFIX_REJECTED
    if (a.status in ("pending", "confirmed")) and a.start_at > now:
        return strings.CLIENT_PAGE_SUFFIX_FUTURE
    return ""


def _history_emoji(a: Appointment, now: datetime) -> str:
    if a.status == "completed":
        return "✅"
    if a.status == "no_show":
        return "❌"
    if a.status in ("cancelled", "rejected"):
        return "❌"
    if a.status in ("pending", "confirmed"):
        return "⏳"
    return "•"


async def _load_history(
    session: AsyncSession, *, master: Master, client_id: UUID
) -> list[Appointment]:
    stmt = (
        select(Appointment)
        .where(
            Appointment.master_id == master.id,
            Appointment.client_id == client_id,
        )
        .order_by(Appointment.start_at.desc())
        .limit(_HISTORY_LIMIT + 1)
    )
    return list((await session.scalars(stmt)).all())


async def _render_client_page(
    *, session: AsyncSession, master: Master, client: Client
) -> tuple[str, InlineKeyboardMarkup]:
    tz = ZoneInfo(master.timezone)
    now = now_utc()
    history = await _load_history(session=session, master=master, client_id=client.id)
    truncated_extra = max(0, len(history) - _HISTORY_LIMIT)
    visible_history = history[:_HISTORY_LIMIT]

    service_ids = {a.service_id for a in visible_history}
    service_names: dict[UUID, str] = {}
    if service_ids:
        rows = await session.scalars(select(Service).where(Service.id.in_(service_ids)))
        for s in rows.all():
            service_names[s.id] = s.name

    header = strings.CLIENT_PAGE_HEADER.format(name=client.name, phone=client.phone)
    notes_body = client.notes if client.notes else strings.CLIENT_PAGE_NOTES_EMPTY
    notes_section = strings.CLIENT_PAGE_NOTES_TITLE.format(notes=notes_body)

    parts = [header, notes_section]
    if not visible_history:
        parts.append(strings.CLIENT_PAGE_HISTORY_EMPTY)
    else:
        parts.append(strings.CLIENT_PAGE_HISTORY_TITLE.format(count=len(visible_history)))
        for a in visible_history:
            local = a.start_at.astimezone(tz)
            parts.append(
                strings.CLIENT_PAGE_HISTORY_LINE.format(
                    emoji=_history_emoji(a, now),
                    dd=f"{local.day:02d}",
                    mm=f"{local.month:02d}",
                    time=f"{local.hour:02d}:{local.minute:02d}",
                    service=service_names.get(a.service_id, "—"),
                    suffix=_history_suffix(a, now),
                )
            )
        if truncated_extra > 0:
            parts.append(strings.CLIENT_PAGE_HISTORY_MORE.format(n=truncated_extra))

    return "\n".join(parts), _client_page_kb(client.id)


@router.message(Command("client"))
async def cmd_client(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await state.clear()
    await state.set_state(MasterView.SearchingClient)
    await message.answer(strings.CLIENT_SEARCH_PROMPT)


@router.message(MasterView.SearchingClient, F.text)
async def msg_search_query(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    q = (message.text or "").strip()
    if len(q) < _MIN_SEARCH:
        await message.answer(strings.CLIENT_SEARCH_TOO_SHORT)
        return
    repo = ClientRepository(session)
    results = await repo.search_by_master(master.id, q, limit=10)
    if not results:
        await message.answer(strings.CLIENT_SEARCH_EMPTY)
        return
    if len(results) == 1:
        await state.clear()
        text, kb = await _render_client_page(
            session=session, master=master, client=results[0]
        )
        await message.answer(text, reply_markup=kb)
        return
    await message.answer(
        strings.CLIENT_SEARCH_PROMPT, reply_markup=_search_results_kb(results)
    )


@router.callback_query(ClientPickCallback.filter())
async def cb_pick_client(
    callback: CallbackQuery,
    callback_data: ClientPickCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    repo = ClientRepository(session)
    client = await repo.get(callback_data.client_id)
    if client is None or client.master_id != master.id:
        await callback.answer(strings.CLIENT_PAGE_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    text, kb = await _render_client_page(
        session=session, master=master, client=client
    )
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(text, reply_markup=kb)


@router.callback_query(ClientNotesEditCallback.filter())
async def cb_edit_notes(
    callback: CallbackQuery,
    callback_data: ClientNotesEditCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(MasterView.EditingNotes)
    await state.update_data(client_id=str(callback_data.client_id))
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.CLIENT_NOTES_PROMPT)


@router.message(MasterView.EditingNotes, F.text)
async def msg_notes_edit(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    data = await state.get_data()
    client_id_raw = data.get("client_id")
    if not isinstance(client_id_raw, str):
        await state.clear()
        return
    client_id = UUID(client_id_raw)
    raw_text = message.text or ""
    cleaned: str | None
    if raw_text.strip() in ("", "-"):
        cleaned = None
    else:
        cleaned = raw_text[:_NOTES_MAX]
    repo = ClientRepository(session)
    await repo.update_notes(client_id, cleaned)
    await session.commit()
    await state.clear()

    client = await repo.get(client_id)
    if client is None:
        await message.answer(strings.CLIENT_NOTES_SAVED)
        return
    text, kb = await _render_client_page(
        session=session, master=master, client=client
    )
    await message.answer(strings.CLIENT_NOTES_SAVED)
    await message.answer(text, reply_markup=kb)


@router.callback_query(ClientAddApptCallback.filter())
async def cb_add_appt(
    callback: CallbackQuery,
    callback_data: ClientAddApptCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    repo = ClientRepository(session)
    client = await repo.get(callback_data.client_id)
    if client is None or client.master_id != master.id:
        await callback.answer(strings.CLIENT_PAGE_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    await state.set_state(MasterAdd.PickingService)
    await state.update_data(client_id=str(client.id))

    services_repo = ServiceRepository(session)
    services = await services_repo.list_active_for_master(master.id)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_ASK_SERVICE,
            reply_markup=services_pick_kb(services),
        )
```

> Note: `services_pick_kb` and `ServiceRepository.list_active_for_master` are both existing from Epic 4/5 (same usage as `add_manual.py`). If the exact import name differs, check `src/keyboards/slots.py` and `src/repositories/services.py` and adjust to match the existing symbol name — do NOT rename existing code.

- [ ] **Step 4: Register the router**

Modify `src/handlers/master/__init__.py` — add `from src.handlers.master.client_page import router as client_page_router` and `router.include_router(client_page_router)` after `calendar_router`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_handlers_master_client_page.py -v`
Expected: PASS (12/12)

- [ ] **Step 6: Run full gates**

Run: `ruff check . && ruff format --check . && mypy src/ && pytest -q`

- [ ] **Step 7: Commit**

```bash
git add src/handlers/master/client_page.py src/handlers/master/__init__.py tests/test_handlers_master_client_page.py
git commit -m "feat(handler): /client search, page, notes edit, add-appt bridge"
```

---

## Task 14: HY translations (user task)

**Files:**
- Modify: `src/strings.py`

This task is handed to the user — same workflow as the end of Epic 5, Task 10. The user replaces every key in the `_HY` block added in Task 4 with the Armenian translation.

- [ ] **Step 1: Print the list of HY keys awaiting translation**

Run:

```bash
python -c "
from src.strings import _HY
ru_ref_keys = [
    'SCHED_DAY_HEADER','SCHED_WORK_HOURS_LINE','SCHED_DAY_OFF_LINE',
    'SCHED_APPTS_SECTION','SCHED_APPTS_EMPTY','SCHED_APPT_LINE',
    'SCHED_FREE_SECTION','SCHED_FREE_NONE',
    'DAY_NAV_TODAY','DAY_NAV_TOMORROW','DAY_NAV_WEEK','DAY_NAV_CALENDAR',
    'DAY_NAV_ADD','DAY_NAV_BACK_TO_WEEK','DAY_NAV_BACK_TO_CALENDAR',
    'MARK_PAST_PRESENT','MARK_PAST_NO_SHOW',
    'MARK_PAST_OK_COMPLETED','MARK_PAST_OK_NO_SHOW',
    'MARK_PAST_NOT_AVAILABLE','MARK_PAST_NOT_ENDED','MARK_PAST_ALREADY_CLOSED',
    'WEEK_HEADER','WEEK_DAY_LINE','WEEK_DAY_LINE_OFF','WEEK_BTN_DAY',
    'CLIENT_SEARCH_PROMPT','CLIENT_SEARCH_TOO_SHORT','CLIENT_SEARCH_EMPTY',
    'CLIENT_PAGE_HEADER','CLIENT_PAGE_NOTES_TITLE','CLIENT_PAGE_NOTES_EMPTY',
    'CLIENT_PAGE_HISTORY_TITLE','CLIENT_PAGE_HISTORY_EMPTY',
    'CLIENT_PAGE_HISTORY_LINE','CLIENT_PAGE_HISTORY_MORE',
    'CLIENT_PAGE_SUFFIX_FUTURE','CLIENT_PAGE_SUFFIX_CANCELLED',
    'CLIENT_PAGE_SUFFIX_REJECTED',
    'CLIENT_PAGE_BTN_EDIT_NOTES','CLIENT_PAGE_BTN_ADD_APPT',
    'CLIENT_PAGE_NOT_FOUND','CLIENT_NOTES_PROMPT','CLIENT_NOTES_SAVED',
]
for k in ru_ref_keys:
    print(f'{k}: {_HY[k]!r}')
"
```

Pipe to user in a formatted block so they translate inline.

- [ ] **Step 2: Wait for the user's translations**

User pastes `HY_KEY: "Armenian text"` pairs back. Apply them by updating the `_HY` block in `src/strings.py`. Any formatting placeholders (`{name}`, `{time}`, `{dd}`, …) must be preserved verbatim.

- [ ] **Step 3: Run tests and gates**

Run: `pytest -q && ruff check . && ruff format --check . && mypy src/`
Expected: all green (same test count as after Task 13). The `test_strings_epic6_keys.py` tests remain the guardrail — they only assert that each key resolves to a `str`, so they are indifferent to the exact Armenian text.

- [ ] **Step 4: Commit**

```bash
git add src/strings.py
git commit -m "i18n(hy): Epic 6 translations"
```

- [ ] **Step 5: Tag the epic**

```bash
git tag -a v0.6.0-epic-6 -m "Epic 6: schedule views (/today /tomorrow /week /calendar /client + mark past)"
```

(Do NOT push unless the user asks.)

---

## Self-Review Notes

- **Spec coverage:** Day schedule renderer (Task 8), `/today`+`/tomorrow` with mark-past (Tasks 9+10), `/week` snapshot (Task 11), `/calendar` with past-month nav (Task 12 + Task 7 keyboard patch), `/client` search+page+notes+bridge (Task 13). All 6.1–6.3 covered.
- **Type consistency:** `list_for_master_range` defined in Task 1 with `statuses: tuple[str, ...] | None = None` — referenced identically in Tasks 9, 11, 12. `mark_completed`/`mark_no_show` signatures in Task 3 match usage in Task 10. `MasterView` states (`SearchingClient`, `EditingNotes`) defined in Task 6 — both used in Task 13.
- **Cross-task dependencies:** Task 9's `cb_day_nav` initially omits `week`/`calendar` branches; Tasks 11 and 12 re-enable them. This avoids the mypy "import cycle" trap and keeps each task independently committable.
- **Testing:** +~45 tests total across 8 new test files (range query 4, notes 4, mark 6, strings 2, callbacks 3, fsm 1, calendar kb 4, schedule_format 5, today 4, mark_past 3, week 3, calendar handler 6, client_page 12 = ~57). Suite moves from 210 to ~267 — comfortably above the spec's ~240 target.
- **Risks flagged in spec addressed:**
  - Message-length: `/week` line template stays short; history cap 20 in Task 13.
  - Mark-past keyboard size: acceptable for v0.1; not gated.
  - Calendar past-month: Task 7 adds `allow_past` param so Task 12 can nav backward.
  - Timezone edge: day ranges computed in `master.timezone` first, then converted to UTC for the query (Task 9 `_render_for`, Task 11 `_collect_week`, Task 12 `_render_day`).
  - Mark-past concurrency: second tap hits `InvalidState("ALREADY_CLOSED")` → alert, no data corruption (Task 3 tests cover this).

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-21-epic-6-schedule-views.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, spec-compliance + code-quality review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch with checkpoints.

Which approach?
