# Эпик 7: Напоминания — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** При подтверждении записи автоматически планировать 3 напоминания (клиент T-24h/T-2h, мастер T-15min), отправлять их в Telegram через APScheduler-polling и авто-отменять просроченные pending.

**Architecture:** Источник правды — таблица `reminders` в Postgres. APScheduler запускает два периодических job'а (каждая минута / каждые 5 минут) с Redis jobstore. Первый job делает `SELECT … FOR UPDATE SKIP LOCKED` и шлёт через `Bot.send_message`. Второй переводит просроченные pending в cancelled. Планирование — side-effect `BookingService.confirm/create_manual`, подавление — вызывается из handler'ов cancel/reject.

**Tech Stack:** APScheduler 3.10, RedisJobStore (reuse `REDIS_URL`), SQLAlchemy 2.0 async, aiogram 3.x, pytest-asyncio, pytest.

**Общие правила (повторить в каждом subagent):**

- Python 3.12, `from __future__ import annotations`, aiogram 3.x, mypy --strict.
- Всё время в БД — UTC через `src/utils/time.now_utc()`. Конвертация в `ZoneInfo(master.timezone)` только на границах (формирование текста для пользователя).
- Запрещено: raw SQL в сервисах/handler'ах, мок MemoryStorage в проде, глобальные мутабельные объекты, комментарии про «что» вместо «почему».
- Все коммиты — атомарные, сообщение на английском в стиле предыдущих (`feat`, `fix`, `refactor`, `test`, `chore`, `docs`). Каждая задача завершается коммитом.
- Квалити-гейты после каждой задачи: `pytest -q && ruff check . && ruff format --check . && mypy src/`. Все зелёные — иначе фиксим.
- `from __future__ import annotations` — **обязательно** в каждом новом .py-файле.

---

## Файловая структура

**Create:**

| Файл | Ответственность |
| --- | --- |
| `migrations/versions/0002_epic7_reminders.py` | Alembic: rename `master_morning` → `master_before`, unique `(appointment_id, kind)`. |
| `src/repositories/reminders.py` | `ReminderRepository`: insert_many, get_due_for_update, mark_sent, suppress_for_appointment. |
| `src/services/reminders.py` | `ReminderService`: schedule_for_appointment, suppress_for_appointment. Использует `ReminderRepository`. |
| `src/scheduler/__init__.py` | Пустой (пакет). |
| `src/scheduler/setup.py` | `build_scheduler(redis_url) -> AsyncIOScheduler` с `RedisJobStore`. |
| `src/scheduler/jobs.py` | `send_due_reminders(bot, session_factory)`, `expire_pending_appointments(bot, session_factory)`. |
| `tests/test_repositories_reminders.py` | БД-тесты `ReminderRepository`. |
| `tests/test_services_reminders.py` | Unit-тесты `ReminderService`. |
| `tests/test_scheduler_jobs.py` | Интеграционные тесты обеих job-функций. |
| `tests/test_strings_epic7_keys.py` | Проверка ключей `REMINDER_*` в `_RU` и `_HY`. |

**Modify:**

| Файл | Что меняется |
| --- | --- |
| `src/db/models.py` | `REMINDER_KINDS = ("day_before", "two_hours", "master_before")`, `UniqueConstraint('appointment_id', 'kind', name='uq_reminders_appointment_kind')` в `__table_args__`. |
| `src/strings.py` | 4 ключа `REMINDER_*` в `_RU` и в `_HY` (HY сначала — копии RU, перевод в финальной задаче). |
| `src/services/booking.py` | `BookingService.__init__` принимает `reminder_service: ReminderService \| None = None`. В `confirm()` и `create_manual()` — `if self._reminder_service is not None: await ...schedule_for_appointment(appt)`. |
| `src/handlers/master/approve.py` | В `cb_confirm`: построить `ReminderService(session)`, передать в `BookingService`. В `cb_reject`: после `svc.reject`, вызвать `reminder_svc.suppress_for_appointment(appt.id)`. |
| `src/handlers/master/add_manual.py` | В handler'е, который делает `create_manual` (~line 495), — аналогично передать `ReminderService`. |
| `src/handlers/client/cancel.py` | После `svc.cancel_by_client`, вызвать `reminder_svc.suppress_for_appointment(appt.id)`. |
| `src/main.py` | Создать `scheduler`, зарегистрировать оба job'а, `scheduler.start()` и `scheduler.shutdown(wait=True)` в try/finally. |

---

## Задачи

### Task 1: Миграция 0002 — переименование master_morning + unique (appointment_id, kind)

**Files:**
- Create: `migrations/versions/0002_epic7_reminders.py`
- Modify: `src/db/models.py` (строки с `REMINDER_KINDS` и `Reminder.__table_args__`)

- [ ] **Step 1: Написать миграцию**

`migrations/versions/0002_epic7_reminders.py`:

```python
"""epic 7: rename master_morning to master_before + unique reminder per appt/kind

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-21 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Data migration first — move any legacy rows to the new label.
    op.execute("UPDATE reminders SET kind = 'master_before' WHERE kind = 'master_morning'")

    # Replace the check constraint.
    op.drop_constraint("ck_reminders_kind", "reminders", type_="check")
    op.create_check_constraint(
        "ck_reminders_kind",
        "reminders",
        "kind IN ('day_before', 'two_hours', 'master_before')",
    )

    # One reminder per (appointment, kind) — makes scheduling idempotent.
    op.create_unique_constraint(
        "uq_reminders_appointment_kind",
        "reminders",
        ["appointment_id", "kind"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_reminders_appointment_kind", "reminders", type_="unique")
    op.drop_constraint("ck_reminders_kind", "reminders", type_="check")
    op.create_check_constraint(
        "ck_reminders_kind",
        "reminders",
        "kind IN ('day_before', 'two_hours', 'master_morning')",
    )
    op.execute("UPDATE reminders SET kind = 'master_morning' WHERE kind = 'master_before'")
```

- [ ] **Step 2: Обновить модель**

`src/db/models.py` — найти строку `REMINDER_KINDS = ("day_before", "two_hours", "master_morning")` и заменить на:

```python
REMINDER_KINDS = ("day_before", "two_hours", "master_before")
```

В `class Reminder.__table_args__` добавить `UniqueConstraint` (импортировать если нет):

```python
    __table_args__ = (
        CheckConstraint("kind IN " + str(REMINDER_KINDS), name="ck_reminders_kind"),
        CheckConstraint("channel IN " + str(REMINDER_CHANNELS), name="ck_reminders_channel"),
        UniqueConstraint("appointment_id", "kind", name="uq_reminders_appointment_kind"),
        Index(
            "ix_reminders_pending_send_at",
            "send_at",
            postgresql_where=text("sent = false"),
        ),
    )
```

Проверить в секции импортов файла — `UniqueConstraint` скорее всего уже импортирован (используется в `Service` и др.). Если нет — добавить к `from sqlalchemy import ...`.

- [ ] **Step 3: Применить миграцию к локальной БД и прогнать гейты**

```bash
source .venv/bin/activate
alembic upgrade head
pytest -q
ruff check .
ruff format --check .
mypy src/
```

Expected:
- `alembic upgrade head` — `Running upgrade 0001 -> 0002, epic 7: rename master_morning ...`
- Все тесты — зелёные (279 passed). Миграция не ломает схему, unique constraint на пустой таблице применяется без ошибок.
- `mypy src/` — `Success: no issues found`.

Если в `src/db/models.py` не хватало импорта `UniqueConstraint` — mypy ругнётся на `NameError` на модуль-уровне — добавить.

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/0002_epic7_reminders.py src/db/models.py
git commit -m "db(mig): rename master_morning to master_before + unique reminder per (appt, kind)"
```

---

### Task 2: Строки RU (+ зеркальный _HY)

**Files:**
- Modify: `src/strings.py` (блоки `_RU` и `_HY`)
- Create: `tests/test_strings_epic7_keys.py`

- [ ] **Step 1: Написать тест присутствия ключей**

`tests/test_strings_epic7_keys.py`:

```python
# ruff: noqa: RUF001
from __future__ import annotations

import pytest

from src.strings import get_bundle

EPIC7_KEYS = [
    "REMINDER_CLIENT_DAY_BEFORE",
    "REMINDER_CLIENT_TWO_HOURS",
    "REMINDER_MASTER_BEFORE",
    "REMINDER_PENDING_EXPIRED",
]


@pytest.mark.parametrize("lang", ["ru", "hy"])
def test_epic7_keys_present(lang: str) -> None:
    bundle = get_bundle(lang)
    for key in EPIC7_KEYS:
        assert hasattr(bundle, key), f"{lang}: missing {key}"
        assert isinstance(getattr(bundle, key), str)


def test_reminder_day_before_has_time_and_service_placeholders() -> None:
    template = get_bundle("ru").REMINDER_CLIENT_DAY_BEFORE
    assert "{time}" in template
    assert "{service}" in template


def test_reminder_two_hours_has_time_and_service_placeholders() -> None:
    template = get_bundle("ru").REMINDER_CLIENT_TWO_HOURS
    assert "{time}" in template
    assert "{service}" in template


def test_reminder_master_has_required_placeholders() -> None:
    template = get_bundle("ru").REMINDER_MASTER_BEFORE
    assert "{time}" in template
    assert "{service}" in template
    assert "{client_name}" in template
    assert "{phone}" in template


def test_reminder_pending_expired_has_required_placeholders() -> None:
    template = get_bundle("ru").REMINDER_PENDING_EXPIRED
    assert "{date}" in template
    assert "{time}" in template
    assert "{service}" in template
```

- [ ] **Step 2: Запустить тест — должен упасть**

```bash
pytest tests/test_strings_epic7_keys.py -v
```

Expected: FAIL (`AttributeError: REMINDER_CLIENT_DAY_BEFORE` — ключи ещё не добавлены).

- [ ] **Step 3: Добавить ключи в `_RU`**

В `src/strings.py` внутри блока `_RU` (словарь начинается со строки `_RU: dict[str, Any] = {`), добавить **в конец** словаря перед закрывающей `}`:

```python
    # --- Epic 7: reminders ---
    "REMINDER_CLIENT_DAY_BEFORE": "⏰ Напоминание: завтра в {time} — {service}.\nЖдём вас!",
    "REMINDER_CLIENT_TWO_HOURS": "⏰ Через 2 часа у вас запись: {service}, {time}.",
    "REMINDER_MASTER_BEFORE": "⏰ Через 15 минут: {client_name} — {service}.\n📞 {phone}",
    "REMINDER_PENDING_EXPIRED": (
        "К сожалению, мастер не подтвердил вашу заявку на {date} {time} — {service}.\n"
        "Попробуйте выбрать другое время: /start"
    ),
```

- [ ] **Step 4: Добавить те же ключи в `_HY` (копия русских, переведём в финальной задаче)**

В блоке `_HY`, в конец перед `}`:

```python
    # --- Epic 7: reminders (HY — awaiting translation, mirrors RU) ---
    "REMINDER_CLIENT_DAY_BEFORE": "⏰ Напоминание: завтра в {time} — {service}.\nЖдём вас!",
    "REMINDER_CLIENT_TWO_HOURS": "⏰ Через 2 часа у вас запись: {service}, {time}.",
    "REMINDER_MASTER_BEFORE": "⏰ Через 15 минут: {client_name} — {service}.\n📞 {phone}",
    "REMINDER_PENDING_EXPIRED": (
        "К сожалению, мастер не подтвердил вашу заявку на {date} {time} — {service}.\n"
        "Попробуйте выбрать другое время: /start"
    ),
```

- [ ] **Step 5: Тест должен пройти**

```bash
pytest tests/test_strings_epic7_keys.py -v
```

Expected: PASS (всё зелёное).

- [ ] **Step 6: Прогнать все гейты и закоммитить**

```bash
pytest -q
ruff check .
ruff format --check .
mypy src/
```

Expected: зелёные, 285+ passed (279 было + 6 новых).

```bash
git add src/strings.py tests/test_strings_epic7_keys.py
git commit -m "i18n: Epic 7 reminder strings (RU + HY mirror)"
```

---

### Task 3: ReminderRepository

**Files:**
- Create: `src/repositories/reminders.py`
- Create: `tests/test_repositories_reminders.py`

**Интерфейс (финальный, всё реализуется в этой задаче):**

```python
class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def insert_many(
        self,
        rows: list[tuple[UUID, str, datetime]],  # (appointment_id, kind, send_at)
    ) -> int: ...
    # Returns number of rows inserted. ON CONFLICT (appointment_id, kind) DO NOTHING.

    async def get_due_for_update(
        self, *, now: datetime, limit: int = 100
    ) -> list[tuple[Reminder, Appointment, Master, Client, Service]]: ...
    # JOIN + FOR UPDATE OF reminders SKIP LOCKED + sent=false AND send_at <= now.

    async def mark_sent(self, reminder_id: UUID, *, sent_at: datetime) -> None: ...

    async def suppress_for_appointment(
        self, appointment_id: UUID, *, now: datetime
    ) -> int: ...
    # UPDATE ... SET sent=true, sent_at=now WHERE appointment_id=$1 AND sent=false
    # Returns number of rows updated.
```

- [ ] **Step 1: Написать failing-тесты**

`tests/test_repositories_reminders.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Reminder, Service
from src.repositories.reminders import ReminderRepository


async def _seed_appt(
    session: AsyncSession,
    *,
    start_at: datetime = datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
    status: str = "confirmed",
) -> tuple[Master, Client, Service, Appointment]:
    master = Master(tg_id=100, name="M", lang="ru", timezone="Asia/Yerevan")
    session.add(master)
    client = Client(tg_id=200, name="C", phone="+37411000000")
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()

    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=60),
        status=status,
        source="client_request",
    )
    session.add(appt)
    await session.flush()
    return master, client, service, appt


@pytest.mark.asyncio
async def test_insert_many_persists_rows(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    send_at = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)

    count = await repo.insert_many([
        (appt.id, "day_before", send_at),
        (appt.id, "two_hours", send_at + timedelta(hours=22)),
    ])

    assert count == 2
    rows = list((await session.scalars(select(Reminder))).all())
    assert len(rows) == 2
    kinds = {r.kind for r in rows}
    assert kinds == {"day_before", "two_hours"}
    assert all(r.sent is False for r in rows)


@pytest.mark.asyncio
async def test_insert_many_idempotent_on_duplicate(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    send_at = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)

    await repo.insert_many([(appt.id, "day_before", send_at)])
    # Second call with same (appointment_id, kind) — ON CONFLICT DO NOTHING.
    count = await repo.insert_many([(appt.id, "day_before", send_at + timedelta(hours=1))])

    assert count == 0
    rows = list((await session.scalars(select(Reminder))).all())
    assert len(rows) == 1
    # Original send_at preserved.
    assert rows[0].send_at == send_at


@pytest.mark.asyncio
async def test_get_due_for_update_returns_only_due_unsent(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    base = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    await repo.insert_many([
        (appt.id, "day_before", base - timedelta(hours=1)),  # due
        (appt.id, "two_hours", base + timedelta(hours=1)),  # not yet due
    ])
    await session.commit()

    rows = await repo.get_due_for_update(now=base, limit=100)
    assert len(rows) == 1
    reminder, appt_row, master_row, client_row, service_row = rows[0]
    assert reminder.kind == "day_before"
    assert appt_row.id == appt.id
    assert master_row.id == appt.master_id
    assert client_row.id == appt.client_id
    assert service_row.id == appt.service_id


@pytest.mark.asyncio
async def test_get_due_for_update_skips_sent(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    base = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    await repo.insert_many([(appt.id, "day_before", base - timedelta(hours=1))])
    await session.commit()

    reminder = (await session.scalars(select(Reminder))).one()
    await repo.mark_sent(reminder.id, sent_at=base)
    await session.commit()

    rows = await repo.get_due_for_update(now=base, limit=100)
    assert rows == []


@pytest.mark.asyncio
async def test_mark_sent_sets_sent_true_and_timestamp(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    send_at = datetime(2026, 5, 3, 12, 0, tzinfo=UTC)

    await repo.insert_many([(appt.id, "day_before", send_at)])
    await session.commit()

    reminder = (await session.scalars(select(Reminder))).one()
    now = datetime(2026, 5, 3, 12, 0, 30, tzinfo=UTC)
    await repo.mark_sent(reminder.id, sent_at=now)

    await session.refresh(reminder)
    assert reminder.sent is True
    assert reminder.sent_at == now


@pytest.mark.asyncio
async def test_suppress_for_appointment_only_marks_unsent(session: AsyncSession) -> None:
    _, _, _, appt = await _seed_appt(session)
    repo = ReminderRepository(session)
    base = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)

    await repo.insert_many([
        (appt.id, "day_before", base - timedelta(hours=1)),
        (appt.id, "two_hours", base + timedelta(hours=1)),
        (appt.id, "master_before", base + timedelta(hours=2)),
    ])
    await session.commit()

    # Pre-mark one as already sent.
    already_sent = (
        await session.scalars(select(Reminder).where(Reminder.kind == "day_before"))
    ).one()
    already_sent.sent = True
    already_sent.sent_at = base - timedelta(minutes=30)
    await session.commit()

    count = await repo.suppress_for_appointment(appt.id, now=base)
    assert count == 2

    all_rows = list((await session.scalars(select(Reminder))).all())
    for r in all_rows:
        assert r.sent is True
    # The one that was already sent keeps its original sent_at.
    still = next(r for r in all_rows if r.kind == "day_before")
    assert still.sent_at == base - timedelta(minutes=30)
```

- [ ] **Step 2: Запустить тест — должен упасть**

```bash
pytest tests/test_repositories_reminders.py -v
```

Expected: FAIL (`ModuleNotFoundError: src.repositories.reminders`).

- [ ] **Step 3: Реализовать репо**

`src/repositories/reminders.py`:

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Reminder, Service


class ReminderRepository:
    """CRUD for `reminders` rows + join-query for the sender worker."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_many(
        self, rows: list[tuple[UUID, str, datetime]]
    ) -> int:
        """Bulk insert with ON CONFLICT (appointment_id, kind) DO NOTHING.

        Returns number of rows actually inserted.
        """
        if not rows:
            return 0
        stmt = (
            pg_insert(Reminder)
            .values(
                [
                    {"appointment_id": appt_id, "kind": kind, "send_at": send_at}
                    for appt_id, kind, send_at in rows
                ]
            )
            .on_conflict_do_nothing(index_elements=["appointment_id", "kind"])
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)

    async def get_due_for_update(
        self, *, now: datetime, limit: int = 100
    ) -> list[tuple[Reminder, Appointment, Master, Client, Service]]:
        """Lock & fetch due reminders with all join-targets loaded.

        Uses FOR UPDATE OF reminders SKIP LOCKED so multiple workers never
        pick up the same row. Ordering by send_at keeps earliest-first.
        """
        stmt = (
            select(Reminder, Appointment, Master, Client, Service)
            .join(Appointment, Reminder.appointment_id == Appointment.id)
            .join(Master, Appointment.master_id == Master.id)
            .join(Client, Appointment.client_id == Client.id)
            .join(Service, Appointment.service_id == Service.id)
            .where(Reminder.sent.is_(False), Reminder.send_at <= now)
            .order_by(Reminder.send_at)
            .limit(limit)
            .with_for_update(of=Reminder, skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return [tuple(row) for row in result.all()]  # type: ignore[misc]

    async def mark_sent(self, reminder_id: UUID, *, sent_at: datetime) -> None:
        stmt = (
            update(Reminder)
            .where(Reminder.id == reminder_id)
            .values(sent=True, sent_at=sent_at)
        )
        await self._session.execute(stmt)

    async def suppress_for_appointment(
        self, appointment_id: UUID, *, now: datetime
    ) -> int:
        """Mark all still-unsent reminders of the appointment as sent (suppressed)."""
        stmt = (
            update(Reminder)
            .where(
                Reminder.appointment_id == appointment_id,
                Reminder.sent.is_(False),
            )
            .values(sent=True, sent_at=now)
        )
        result = await self._session.execute(stmt)
        return int(result.rowcount or 0)
```

- [ ] **Step 4: Запустить тесты — зелёные**

```bash
pytest tests/test_repositories_reminders.py -v
```

Expected: PASS (6/6). Если `type: ignore[misc]` на возвращаемом list comprehension вызывает ошибку в mypy — попробовать `return list(result.all())` и привести каждую строку. Тесты — главный арбитр.

- [ ] **Step 5: Гейты и коммит**

```bash
pytest -q
ruff check .
ruff format --check .
mypy src/
```

Expected: зелёные.

```bash
git add src/repositories/reminders.py tests/test_repositories_reminders.py
git commit -m "feat(repo): ReminderRepository with FOR UPDATE SKIP LOCKED and ON CONFLICT"
```

---

### Task 4: ReminderService.schedule_for_appointment

**Files:**
- Create: `src/services/reminders.py`
- Create: `tests/test_services_reminders.py`

- [ ] **Step 1: Написать failing-тесты**

`tests/test_services_reminders.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Reminder, Service
from src.services.reminders import ReminderService


async def _seed_appt(
    session: AsyncSession, *, start_at: datetime
) -> Appointment:
    master = Master(tg_id=100, name="M", lang="ru", timezone="Asia/Yerevan")
    session.add(master)
    client = Client(tg_id=200, name="C", phone="+37411000000")
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()

    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=60),
        status="confirmed",
        source="client_request",
    )
    session.add(appt)
    await session.flush()
    return appt


@pytest.mark.asyncio
async def test_schedule_creates_three_reminders_when_all_future(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    now = start - timedelta(days=2)
    appt = await _seed_appt(session, start_at=start)

    svc = ReminderService(session)
    count = await svc.schedule_for_appointment(appt, now=now)

    assert count == 3
    rows = list((await session.scalars(select(Reminder))).all())
    by_kind = {r.kind: r for r in rows}
    assert set(by_kind) == {"day_before", "two_hours", "master_before"}
    assert by_kind["day_before"].send_at == start - timedelta(hours=24)
    assert by_kind["two_hours"].send_at == start - timedelta(hours=2)
    assert by_kind["master_before"].send_at == start - timedelta(minutes=15)


@pytest.mark.asyncio
async def test_schedule_skips_day_before_when_less_than_24h(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    now = start - timedelta(hours=20)  # <24h — skip day_before
    appt = await _seed_appt(session, start_at=start)

    svc = ReminderService(session)
    count = await svc.schedule_for_appointment(appt, now=now)

    assert count == 2
    kinds = {r.kind for r in (await session.scalars(select(Reminder))).all()}
    assert kinds == {"two_hours", "master_before"}


@pytest.mark.asyncio
async def test_schedule_skips_all_when_less_than_15min(
    session: AsyncSession,
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    now = start - timedelta(minutes=10)  # <15min — nothing to schedule
    appt = await _seed_appt(session, start_at=start)

    svc = ReminderService(session)
    count = await svc.schedule_for_appointment(appt, now=now)

    assert count == 0
    assert (await session.scalars(select(Reminder))).all() == []


@pytest.mark.asyncio
async def test_schedule_is_idempotent(session: AsyncSession) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    now = start - timedelta(days=2)
    appt = await _seed_appt(session, start_at=start)

    svc = ReminderService(session)
    await svc.schedule_for_appointment(appt, now=now)
    second = await svc.schedule_for_appointment(appt, now=now)

    assert second == 0
    rows = list((await session.scalars(select(Reminder))).all())
    assert len(rows) == 3
```

- [ ] **Step 2: Тест должен упасть**

```bash
pytest tests/test_services_reminders.py -v
```

Expected: FAIL (`ModuleNotFoundError: src.services.reminders`).

- [ ] **Step 3: Реализовать сервис (только schedule — suppress будет в Task 5)**

`src/services/reminders.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment
from src.repositories.reminders import ReminderRepository
from src.utils.time import now_utc


# Fixed offsets from appointment start_at (UTC).
_OFFSETS: list[tuple[str, timedelta]] = [
    ("day_before", timedelta(hours=24)),
    ("two_hours", timedelta(hours=2)),
    ("master_before", timedelta(minutes=15)),
]


class ReminderService:
    """Plan + suppress `reminders` rows around appointment lifecycle events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ReminderRepository(session)

    async def schedule_for_appointment(
        self, appointment: Appointment, *, now: datetime | None = None
    ) -> int:
        """Create up to 3 reminder rows (skipping those whose send_at is already in the past).

        Idempotent — relies on UNIQUE(appointment_id, kind) + ON CONFLICT DO NOTHING.
        Returns the count of newly inserted rows.
        """
        n = now if now is not None else now_utc()
        rows: list[tuple[UUID, str, datetime]] = []
        for kind, offset in _OFFSETS:
            send_at = appointment.start_at - offset
            if send_at > n:
                rows.append((appointment.id, kind, send_at))
        return await self._repo.insert_many(rows)
```

- [ ] **Step 4: Тесты должны пройти**

```bash
pytest tests/test_services_reminders.py -v
```

Expected: PASS (4/4).

- [ ] **Step 5: Гейты и коммит**

```bash
pytest -q
ruff check .
ruff format --check .
mypy src/
```

Expected: зелёные.

```bash
git add src/services/reminders.py tests/test_services_reminders.py
git commit -m "feat(service): ReminderService.schedule_for_appointment"
```

---

### Task 5: ReminderService.suppress_for_appointment

**Files:**
- Modify: `src/services/reminders.py`
- Modify: `tests/test_services_reminders.py`

- [ ] **Step 1: Добавить failing-тесты в существующий файл**

Добавить в конец `tests/test_services_reminders.py`:

```python
@pytest.mark.asyncio
async def test_suppress_marks_all_unsent(session: AsyncSession) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    now = start - timedelta(days=2)
    appt = await _seed_appt(session, start_at=start)

    svc = ReminderService(session)
    await svc.schedule_for_appointment(appt, now=now)

    suppress_now = start - timedelta(hours=23)
    count = await svc.suppress_for_appointment(appt.id, now=suppress_now)

    assert count == 3
    rows = list((await session.scalars(select(Reminder))).all())
    for r in rows:
        assert r.sent is True
        assert r.sent_at == suppress_now


@pytest.mark.asyncio
async def test_suppress_no_op_when_no_reminders(session: AsyncSession) -> None:
    svc = ReminderService(session)
    count = await svc.suppress_for_appointment(uuid4(), now=datetime.now(UTC))
    assert count == 0
```

- [ ] **Step 2: Тесты должны упасть**

```bash
pytest tests/test_services_reminders.py::test_suppress_marks_all_unsent -v
```

Expected: FAIL (`AttributeError: 'ReminderService' object has no attribute 'suppress_for_appointment'`).

- [ ] **Step 3: Добавить метод**

В `src/services/reminders.py` внутри класса `ReminderService`, после `schedule_for_appointment`:

```python
    async def suppress_for_appointment(
        self, appointment_id: UUID, *, now: datetime | None = None
    ) -> int:
        """Mark all unsent reminders of an appointment as sent (no send).

        Called when the appointment is cancelled/rejected so the worker won't
        pick them up. The worker's status check is a fallback, not the primary
        gate — this is cheaper than scanning on every tick.
        """
        n = now if now is not None else now_utc()
        return await self._repo.suppress_for_appointment(appointment_id, now=n)
```

- [ ] **Step 4: Тесты зелёные**

```bash
pytest tests/test_services_reminders.py -v
```

Expected: PASS (6/6).

- [ ] **Step 5: Гейты и коммит**

```bash
pytest -q
ruff check .
ruff format --check .
mypy src/
```

Expected: зелёные.

```bash
git add src/services/reminders.py tests/test_services_reminders.py
git commit -m "feat(service): ReminderService.suppress_for_appointment"
```

---

### Task 6: Интегрировать schedule в BookingService (confirm + create_manual)

**Files:**
- Modify: `src/services/booking.py`
- Modify: `src/handlers/master/approve.py`
- Modify: `src/handlers/master/add_manual.py`
- Modify: `tests/test_handlers_master_approve.py`
- Modify: `tests/test_handlers_master_add_part_b.py` (существующий тест /add)

**Design:** `BookingService.__init__` приобретает опциональный параметр `reminder_service: ReminderService | None = None`. Если не None — `confirm()` и `create_manual()` вызывают `await reminder_service.schedule_for_appointment(appt)` в той же сессии, до коммита (в `confirm` коммит делает middleware, в `create_manual` — сам метод).

Все существующие unit-тесты `BookingService` продолжают работать: они конструируют `BookingService(session)` без `reminder_service`, ветка scheduling отключена.

Handler'ы теперь собирают обе службы:

```python
reminder_svc = ReminderService(session)
svc = BookingService(session, reminder_service=reminder_svc)
```

- [ ] **Step 1: Написать failing-тест в `tests/test_handlers_master_approve.py`**

Добавить в конец файла:

```python
@pytest.mark.asyncio
async def test_confirm_schedules_three_reminders(session: AsyncSession) -> None:
    from sqlalchemy import select

    from src.db.models import Reminder
    from src.handlers.master.approve import cb_confirm

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    # start in ~5 days so all three reminders are future.
    appt = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=datetime(2030, 5, 4, 12, 0, tzinfo=UTC),
        end_at=datetime(2030, 5, 4, 13, 0, tzinfo=UTC),
        status="pending",
        source="client_request",
        decision_deadline=datetime(2030, 5, 4, 10, 0, tzinfo=UTC),
    )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id), text="🔔 Новая заявка")
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="confirm", appointment_id=appt.id)

    await cb_confirm(cb, callback_data=cb_data, master=master, session=session, bot=bot)
    await session.commit()

    kinds = {r.kind for r in (await session.scalars(select(Reminder))).all()}
    assert kinds == {"day_before", "two_hours", "master_before"}
```

- [ ] **Step 2: Тест должен упасть**

```bash
pytest tests/test_handlers_master_approve.py::test_confirm_schedules_three_reminders -v
```

Expected: FAIL (`AssertionError: assert set() == {'day_before', ...}`).

- [ ] **Step 3: Расширить `BookingService.__init__`**

В `src/services/booking.py`:

```python
from src.services.reminders import ReminderService  # add to imports
```

Заменить `__init__`:

```python
    def __init__(
        self,
        session: AsyncSession,
        *,
        reminder_service: ReminderService | None = None,
    ) -> None:
        self._session = session
        self._repo = AppointmentRepository(session)
        self._reminder_service = reminder_service
```

В методе `confirm(...)` — заменить тело:

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
        if self._reminder_service is not None:
            await self._reminder_service.schedule_for_appointment(appt, now=n)
        return appt
```

В методе `create_manual(...)` — заменить так, чтобы scheduling был **до** `await self._session.commit()`:

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
            if self._reminder_service is not None:
                await self._session.flush()
                await self._reminder_service.schedule_for_appointment(appt, now=n)
            await self._session.commit()
            return appt
        except IntegrityError as exc:
            await self._session.rollback()
            raise SlotAlreadyTaken(str(start_at)) from exc
```

- [ ] **Step 4: Обновить handler cb_confirm в `src/handlers/master/approve.py`**

Найти тело `cb_confirm` (около строки 75). Заменить строку `svc = BookingService(session)` на:

```python
    from src.services.reminders import ReminderService  # local import to keep top clean

    reminder_svc = ReminderService(session)
    svc = BookingService(session, reminder_service=reminder_svc)
```

(Импорт на верх файла также ок. Выбрать один стиль — предпочтительно top-level импорт, если у handler'а нет circular-import риска; у этого нет.)

- [ ] **Step 5: Обновить handler `/add` confirm-step в `src/handlers/master/add_manual.py`**

Открыть файл, найти место вызова `svc.create_manual(...)` (около строки 495). Заменить строку `svc = BookingService(session)` (или аналогичную в том же handler'е) на:

```python
    from src.services.reminders import ReminderService

    reminder_svc = ReminderService(session)
    svc = BookingService(session, reminder_service=reminder_svc)
```

Если в handler'е BookingService создаётся на нескольких шагах — обновить только тот, что делает `create_manual`.

- [ ] **Step 6: Добавить тест scheduling на уровне BookingService.create_manual**

Новый файл `tests/test_services_booking_epic7.py` (ниже — полный тест, вставить целиком). Этот тест проверяет: если в `BookingService` передан `ReminderService`, то `create_manual` в ту же транзакцию планирует 3 напоминания.

```python
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master, Reminder, Service
from src.services.booking import BookingService
from src.services.reminders import ReminderService


@pytest.mark.asyncio
async def test_create_manual_with_reminder_service_schedules_three(
    session: AsyncSession,
) -> None:
    master = Master(tg_id=1, name="M", lang="ru", timezone="Asia/Yerevan")
    session.add(master)
    client = Client(tg_id=2, name="C", phone="+37411000000")
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    reminder_svc = ReminderService(session)
    svc = BookingService(session, reminder_service=reminder_svc)

    start = datetime(2030, 5, 4, 12, 0, tzinfo=UTC)
    appt = await svc.create_manual(
        master=master, client=client, service=service, start_at=start,
        now=datetime(2030, 5, 1, 0, 0, tzinfo=UTC),
    )

    kinds = {r.kind for r in (await session.scalars(select(Reminder))).all()}
    assert kinds == {"day_before", "two_hours", "master_before"}
    assert appt.status == "confirmed"
```

- [ ] **Step 7: Все тесты зелёные**

```bash
pytest -q
```

Expected: PASS. Старые тесты `BookingService(session)` продолжают работать (reminder_service=None → никакого scheduling).

- [ ] **Step 8: Гейты и коммит**

```bash
ruff check .
ruff format --check .
mypy src/
```

```bash
git add src/services/booking.py src/handlers/master/approve.py \
        src/handlers/master/add_manual.py \
        tests/test_handlers_master_approve.py tests/test_services_booking_epic7.py
git commit -m "feat(booking): inject ReminderService — schedule on confirm/create_manual"
```

---

### Task 7: Интегрировать suppress в cancel/reject flows

**Files:**
- Modify: `src/handlers/master/approve.py` (cb_reject)
- Modify: `src/handlers/client/cancel.py`
- Modify: `tests/test_handlers_master_approve.py`
- Modify: `tests/test_handlers_client_cancel.py`

**Design:** handler после успешного `svc.reject(...)` / `svc.cancel_by_client(...)` вызывает `await reminder_svc.suppress_for_appointment(appt.id)`. Middleware коммитит атомарно. Pending у `reject` обычно не имеет reminders (создаются только на confirm) — но вызов дешёв и защищает от race: если между confirm и reject что-то странное, suppress пометит.

- [ ] **Step 1: Failing-тест для reject**

В `tests/test_handlers_master_approve.py` добавить:

```python
@pytest.mark.asyncio
async def test_reject_suppresses_existing_reminders(session: AsyncSession) -> None:
    from sqlalchemy import select

    from src.db.models import Reminder
    from src.handlers.master.approve import cb_reject

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=datetime(2030, 5, 4, 12, 0, tzinfo=UTC),
        end_at=datetime(2030, 5, 4, 13, 0, tzinfo=UTC),
        status="pending",
        source="client_request",
        decision_deadline=datetime(2030, 5, 4, 10, 0, tzinfo=UTC),
    )
    # Artificially plant a reminder (hypothetical race scenario).
    reminder = Reminder(
        appointment_id=appt.id,
        kind="day_before",
        send_at=datetime(2030, 5, 3, 12, 0, tzinfo=UTC),
    )
    session.add(reminder)
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id), text="🔔")
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="reject", appointment_id=appt.id)

    await cb_reject(cb, callback_data=cb_data, master=master, session=session, bot=bot)
    await session.commit()

    await session.refresh(reminder)
    assert reminder.sent is True
```

- [ ] **Step 2: Failing-тест для cancel_by_client**

В `tests/test_handlers_client_cancel.py` добавить аналогичный:

```python
@pytest.mark.asyncio
async def test_client_cancel_suppresses_reminders(session: AsyncSession) -> None:
    from sqlalchemy import select

    from src.db.models import Reminder

    # Reuse the seeding helper already in the file (_seed or similar).
    # The test must: seed appt (confirmed), plant a Reminder, call cancel handler,
    # assert reminder.sent is True.
    # Use the existing test `test_client_cancel_happy_path` as template.
    # If no helper exists — inline the seeding. Do NOT leave this stub.
```

**Subagent'у:** стаб выше — не плейсхолдер, а инструкция. Посмотри существующий `test_client_cancel_happy_path` (или ближайший live-тест) в том же файле, используй тот же seed-паттерн, добавь планирование reminder'а и проверь `reminder.sent` после вызова handler'а.

- [ ] **Step 3: Тесты должны упасть**

```bash
pytest tests/test_handlers_master_approve.py::test_reject_suppresses_existing_reminders \
       tests/test_handlers_client_cancel.py::test_client_cancel_suppresses_reminders -v
```

Expected: FAIL (reminder остаётся `sent=False`).

- [ ] **Step 4: Обновить cb_reject в `src/handlers/master/approve.py`**

В теле `cb_reject` — после успешного `svc.reject(...)` (до `_notify_client` если уведомление делается):

```python
    # ... svc.reject(...) вызывается как сейчас ...
    from src.services.reminders import ReminderService

    reminder_svc = ReminderService(session)
    await reminder_svc.suppress_for_appointment(appt.id)
```

(Если импорты на верх файла — предпочитать верх.)

- [ ] **Step 5: Обновить cancel_by_client в `src/handlers/client/cancel.py`**

После `appt, client, master, service = await svc.cancel_by_client(...)`:

```python
    from src.services.reminders import ReminderService

    reminder_svc = ReminderService(session)
    await reminder_svc.suppress_for_appointment(appt.id)
```

- [ ] **Step 6: Тесты зелёные**

```bash
pytest tests/test_handlers_master_approve.py tests/test_handlers_client_cancel.py -v
```

Expected: PASS.

- [ ] **Step 7: Гейты и коммит**

```bash
pytest -q
ruff check .
ruff format --check .
mypy src/
```

Expected: зелёные.

```bash
git add src/handlers/master/approve.py src/handlers/client/cancel.py \
        tests/test_handlers_master_approve.py tests/test_handlers_client_cancel.py
git commit -m "feat(handler): suppress reminders on reject/client-cancel"
```

---

### Task 8: Scheduler setup

**Files:**
- Create: `src/scheduler/__init__.py` (пустой)
- Create: `src/scheduler/setup.py`
- Create: `tests/test_scheduler_setup.py`

- [ ] **Step 1: Failing-тест**

`tests/test_scheduler_setup.py`:

```python
from __future__ import annotations

from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.scheduler.setup import build_scheduler


def test_build_scheduler_uses_redis_jobstore_from_url() -> None:
    sched = build_scheduler("redis://localhost:6379/0")
    assert isinstance(sched, AsyncIOScheduler)
    default_store = sched._jobstores["default"]  # type: ignore[attr-defined]
    assert isinstance(default_store, RedisJobStore)


def test_build_scheduler_returns_scheduler_not_running() -> None:
    sched = build_scheduler("redis://localhost:6379/0")
    assert sched.running is False
```

- [ ] **Step 2: Тест должен упасть**

```bash
pytest tests/test_scheduler_setup.py -v
```

Expected: FAIL (`ModuleNotFoundError: src.scheduler.setup`).

- [ ] **Step 3: Создать пакет и модуль**

`src/scheduler/__init__.py` — пустой файл.

`src/scheduler/setup.py`:

```python
from __future__ import annotations

from urllib.parse import urlparse

from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler


def build_scheduler(redis_url: str) -> AsyncIOScheduler:
    """Build AsyncIOScheduler with RedisJobStore from a `redis://host:port/db` URL.

    The scheduler is not started — caller owns start/stop.
    """
    parsed = urlparse(redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    db = int((parsed.path or "/0").lstrip("/") or 0)

    jobstores = {"default": RedisJobStore(host=host, port=port, db=db)}
    return AsyncIOScheduler(jobstores=jobstores, timezone="UTC")
```

- [ ] **Step 4: Тест зелёный**

```bash
pytest tests/test_scheduler_setup.py -v
```

Expected: PASS (2/2).

- [ ] **Step 5: Гейты и коммит**

```bash
pytest -q
ruff check .
ruff format --check .
mypy src/
```

Expected: зелёные. Если mypy ругается на отсутствие стабов `apscheduler` — в `pyproject.toml` уже есть override `module = ["apscheduler.*", ...]`, так что должно быть ок.

```bash
git add src/scheduler/__init__.py src/scheduler/setup.py tests/test_scheduler_setup.py
git commit -m "feat(scheduler): build_scheduler with RedisJobStore"
```

---

### Task 9: Job `send_due_reminders`

**Files:**
- Create: `src/scheduler/jobs.py`
- Create: `tests/test_scheduler_jobs.py`

- [ ] **Step 1: Failing-тесты**

`tests/test_scheduler_jobs.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.db.models import Appointment, Client, Master, Reminder, Service
from src.scheduler.jobs import send_due_reminders
from src.services.reminders import ReminderService


async def _seed_confirmed(
    session: AsyncSession, *, start_at: datetime
) -> tuple[Master, Client, Service, Appointment]:
    master = Master(tg_id=111, name="M", lang="ru", timezone="Asia/Yerevan")
    session.add(master)
    client = Client(tg_id=222, name="Иван", phone="+37411000111")
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()

    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=60),
        status="confirmed",
        source="client_request",
    )
    session.add(appt)
    await session.flush()
    return master, client, service, appt


@pytest.mark.asyncio
async def test_sends_due_client_reminder(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    master, client, service, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(days=2))
    await session.commit()

    bot = AsyncMock()
    # Freeze "now" past day_before but before two_hours.
    now = start - timedelta(hours=23)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == client.tg_id

    # Check DB state: day_before marked sent, others untouched.
    async with session_maker() as s:
        rows = list((await s.scalars(select(Reminder))).all())
        by_kind = {r.kind: r for r in rows}
        assert by_kind["day_before"].sent is True
        assert by_kind["two_hours"].sent is False
        assert by_kind["master_before"].sent is False


@pytest.mark.asyncio
async def test_skips_cancelled_appointment(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    master, client, service, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(days=2))
    # Cancel the appointment but leave reminder rows intact.
    appt.status = "cancelled"
    await session.commit()

    bot = AsyncMock()
    now = start - timedelta(hours=23)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    bot.send_message.assert_not_awaited()
    # Reminder is lazily marked sent=true so we don't re-visit it.
    async with session_maker() as s:
        by_kind = {r.kind: r for r in (await s.scalars(select(Reminder))).all()}
        assert by_kind["day_before"].sent is True


@pytest.mark.asyncio
async def test_future_reminders_untouched(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    _, _, _, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(days=2))
    await session.commit()

    bot = AsyncMock()
    # Before any send_at.
    now = start - timedelta(days=3)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    bot.send_message.assert_not_awaited()
    async with session_maker() as s:
        assert all(
            r.sent is False for r in (await s.scalars(select(Reminder))).all()
        )


@pytest.mark.asyncio
async def test_telegram_forbidden_marks_sent(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    _, _, _, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(days=2))
    await session.commit()

    bot = AsyncMock()
    bot.send_message.side_effect = TelegramBadRequest(
        method=None, message="chat not found"  # type: ignore[arg-type]
    )

    now = start - timedelta(hours=23)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    # Still marked sent=true — we don't retry dead chats forever.
    async with session_maker() as s:
        by_kind = {r.kind: r for r in (await s.scalars(select(Reminder))).all()}
        assert by_kind["day_before"].sent is True


@pytest.mark.asyncio
async def test_master_reminder_goes_to_master_chat(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    master, client, service, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(days=2))
    await session.commit()

    bot = AsyncMock()
    # 10 min before start — only master_before is due.
    now = start - timedelta(minutes=10)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == master.tg_id
    assert "Иван" in kwargs["text"]
    assert "Стрижка" in kwargs["text"]


@pytest.mark.asyncio
async def test_idempotent_second_run_no_resend(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    _, _, _, appt = await _seed_confirmed(session, start_at=start)
    reminder_svc = ReminderService(session)
    await reminder_svc.schedule_for_appointment(appt, now=start - timedelta(days=2))
    await session.commit()

    bot = AsyncMock()
    now = start - timedelta(hours=23)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)
    await send_due_reminders(bot=bot, session_factory=session_maker, now=now)

    # day_before fired once, not twice.
    assert bot.send_message.await_count == 1
```

- [ ] **Step 2: Тесты должны упасть**

```bash
pytest tests/test_scheduler_jobs.py -v
```

Expected: FAIL (module not found).

- [ ] **Step 3: Реализовать `send_due_reminders`**

`src/scheduler/jobs.py`:

```python
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Appointment, Client, Master, Reminder, Service
from src.repositories.reminders import ReminderRepository
from src.strings import strings
from src.utils.time import now_utc

log: structlog.stdlib.BoundLogger = structlog.get_logger()


_CLIENT_KINDS = {"day_before", "two_hours"}
_MASTER_KINDS = {"master_before"}


def _format_reminder(
    reminder: Reminder,
    master: Master,
    client: Client,
    service: Service,
    appointment: Appointment,
) -> tuple[int, str]:
    """Return (chat_id, text) for the reminder. Uses master.timezone for the {time} slot."""
    tz = ZoneInfo(master.timezone)
    local = appointment.start_at.astimezone(tz)
    time_s = local.strftime("%H:%M")

    if reminder.kind == "day_before":
        return client.tg_id, strings.REMINDER_CLIENT_DAY_BEFORE.format(
            time=time_s, service=service.name
        )
    if reminder.kind == "two_hours":
        return client.tg_id, strings.REMINDER_CLIENT_TWO_HOURS.format(
            time=time_s, service=service.name
        )
    if reminder.kind == "master_before":
        return master.tg_id, strings.REMINDER_MASTER_BEFORE.format(
            time=time_s,
            service=service.name,
            client_name=client.name,
            phone=client.phone or "",
        )
    raise ValueError(f"unknown reminder kind: {reminder.kind!r}")


async def send_due_reminders(
    *,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    now: datetime | None = None,
) -> None:
    """One-tick worker: pick due reminders and send them.

    - FOR UPDATE SKIP LOCKED (in ReminderRepository.get_due_for_update) makes
      concurrent ticks safe.
    - If appointment.status != 'confirmed', reminder is marked sent without
      firing — lazy cleanup of dead rows.
    - TelegramBadRequest / TelegramForbiddenError also mark sent (don't retry
      forever).
    - TelegramRetryAfter leaves sent=false — next tick retries.
    - Any other exception leaves sent=false and logs.
    """
    n = now if now is not None else now_utc()
    async with session_factory() as session:
        repo = ReminderRepository(session)
        rows = await repo.get_due_for_update(now=n, limit=100)

        for reminder, appointment, master, client, service in rows:
            if appointment.status != "confirmed":
                await repo.mark_sent(reminder.id, sent_at=n)
                continue

            chat_id, text = _format_reminder(
                reminder, master, client, service, appointment
            )
            try:
                await bot.send_message(chat_id=chat_id, text=text)
            except TelegramRetryAfter as exc:
                log.warning(
                    "reminder_retry_after",
                    reminder_id=str(reminder.id),
                    retry_after=exc.retry_after,
                )
                continue  # leave sent=false
            except (TelegramBadRequest, TelegramForbiddenError) as exc:
                log.warning(
                    "reminder_dead_chat",
                    reminder_id=str(reminder.id),
                    chat_id=chat_id,
                    error=repr(exc),
                )
                await repo.mark_sent(reminder.id, sent_at=n)
                continue
            except Exception as exc:  # pragma: no cover
                log.error(
                    "reminder_send_failed",
                    reminder_id=str(reminder.id),
                    error=repr(exc),
                )
                continue

            await repo.mark_sent(reminder.id, sent_at=n)

        await session.commit()
```

- [ ] **Step 4: Тесты зелёные**

```bash
pytest tests/test_scheduler_jobs.py -v
```

Expected: PASS (6/6).

Если тест `test_telegram_forbidden_marks_sent` падает из-за невалидного конструктора `TelegramBadRequest` в этой версии aiogram — подобрать аргументы из `help(TelegramBadRequest)` (в aiogram 3.x это `method: TelegramMethod, message: str`). В крайнем случае — инстанциировать через `mock` с тем же классом.

- [ ] **Step 5: Гейты и коммит**

```bash
pytest -q
ruff check .
ruff format --check .
mypy src/
```

Expected: зелёные.

```bash
git add src/scheduler/jobs.py tests/test_scheduler_jobs.py
git commit -m "feat(scheduler): send_due_reminders job"
```

---

### Task 10: Job `expire_pending_appointments`

**Files:**
- Modify: `src/scheduler/jobs.py`
- Modify: `tests/test_scheduler_jobs.py`

- [ ] **Step 1: Failing-тест**

Добавить в `tests/test_scheduler_jobs.py`:

```python
@pytest.mark.asyncio
async def test_expire_pending_cancels_overdue_and_notifies(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    from src.scheduler.jobs import expire_pending_appointments

    master = Master(tg_id=401, name="M", lang="ru", timezone="Asia/Yerevan")
    session.add(master)
    client = Client(tg_id=402, name="Анна", phone="+37411000401")
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    deadline = datetime(2026, 5, 3, 10, 0, tzinfo=UTC)
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(hours=1),
        status="pending",
        source="client_request",
        decision_deadline=deadline,
    )
    session.add(appt)
    await session.commit()

    bot = AsyncMock()
    now = deadline + timedelta(hours=1)  # past deadline

    await expire_pending_appointments(bot=bot, session_factory=session_maker, now=now)

    async with session_maker() as s:
        refreshed = await s.get(Appointment, appt.id)
        assert refreshed is not None
        assert refreshed.status == "cancelled"
        assert refreshed.cancelled_by == "system"

    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == client.tg_id
    assert "04.05" in kwargs["text"]


@pytest.mark.asyncio
async def test_expire_pending_leaves_fresh_pending(
    session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    from src.scheduler.jobs import expire_pending_appointments

    master = Master(tg_id=501, name="M", lang="ru", timezone="Asia/Yerevan")
    session.add(master)
    client = Client(tg_id=502, name="C", phone="+37411000501")
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()
    start = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    deadline = datetime(2026, 5, 3, 10, 0, tzinfo=UTC)  # in the past
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(hours=1),
        status="pending",
        source="client_request",
        decision_deadline=deadline,
    )
    session.add(appt)
    await session.commit()

    bot = AsyncMock()
    # now is BEFORE deadline → shouldn't expire.
    now = deadline - timedelta(hours=1)

    await expire_pending_appointments(bot=bot, session_factory=session_maker, now=now)

    async with session_maker() as s:
        refreshed = await s.get(Appointment, appt.id)
        assert refreshed is not None
        assert refreshed.status == "pending"
    bot.send_message.assert_not_awaited()
```

- [ ] **Step 2: Тесты должны упасть**

```bash
pytest tests/test_scheduler_jobs.py::test_expire_pending_cancels_overdue_and_notifies -v
```

Expected: FAIL (`ImportError: cannot import name 'expire_pending_appointments'`).

- [ ] **Step 3: Реализовать**

Добавить в `src/scheduler/jobs.py`:

```python
from src.repositories.appointments import AppointmentRepository
from src.services.booking import BookingService


async def expire_pending_appointments(
    *,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    now: datetime | None = None,
) -> None:
    """Transition pending appointments past their decision_deadline to cancelled(system).

    Notifies the client. Does NOT notify the master — it was their inaction that caused
    the cancellation.
    """
    n = now if now is not None else now_utc()
    async with session_factory() as session:
        a_repo = AppointmentRepository(session)
        pending = await a_repo.get_pending_past_deadline(now=n)
        if not pending:
            return

        svc = BookingService(session)
        for appt in pending:
            try:
                await svc.cancel(appt.id, cancelled_by="system", now=n)
            except Exception as exc:  # pragma: no cover
                log.error(
                    "pending_expire_cancel_failed",
                    appointment_id=str(appt.id),
                    error=repr(exc),
                )
                continue

            client = await session.get(Client, appt.client_id)
            service = await session.get(Service, appt.service_id)
            master = await session.get(Master, appt.master_id)
            if client is None or service is None or master is None:
                continue

            tz = ZoneInfo(master.timezone)
            local = appt.start_at.astimezone(tz)
            text = strings.REMINDER_PENDING_EXPIRED.format(
                date=local.strftime("%d.%m"),
                time=local.strftime("%H:%M"),
                service=service.name,
            )
            try:
                await bot.send_message(chat_id=client.tg_id, text=text)
            except (TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter) as exc:
                log.warning(
                    "pending_expire_notify_failed",
                    appointment_id=str(appt.id),
                    chat_id=client.tg_id,
                    error=repr(exc),
                )

        await session.commit()
```

- [ ] **Step 4: Тесты зелёные**

```bash
pytest tests/test_scheduler_jobs.py -v
```

Expected: PASS (8/8).

- [ ] **Step 5: Гейты и коммит**

```bash
pytest -q
ruff check .
ruff format --check .
mypy src/
```

Expected: зелёные.

```bash
git add src/scheduler/jobs.py tests/test_scheduler_jobs.py
git commit -m "feat(scheduler): expire_pending_appointments job"
```

---

### Task 11: Интеграция scheduler в лайфспан `main.py`

**Files:**
- Modify: `src/main.py`

**Design:** создаём scheduler до `start_polling`, регистрируем оба job'а с фиксированными `id` (`replace_existing=True`), стартуем, в finally — shutdown. `session_factory` = `SessionMaker` (уже глобально объявлен в `src/db/base.py`).

Юнит-теста на лайфспан нет — вместо него смоук-тест после рестарта контейнера (аналогично тому, как запускали бота в конце Эпика 6). Функция тестирования: запустить бота, подождать 2 минуты, посмотреть лог на `reminder_` события.

- [ ] **Step 1: Заменить `main.py`**

Полностью заменить `src/main.py`:

```python
from __future__ import annotations

import asyncio
import logging
from functools import partial

import structlog
from aiogram import Bot, Dispatcher
from apscheduler.triggers.cron import CronTrigger

from src.config import settings
from src.db.base import SessionMaker
from src.fsm_storage import build_fsm_storage
from src.handlers import build_root_router
from src.middlewares.db import DbSessionMiddleware
from src.middlewares.lang import LangMiddleware
from src.middlewares.user import UserMiddleware
from src.scheduler.jobs import expire_pending_appointments, send_due_reminders
from src.scheduler.setup import build_scheduler


def configure_logging() -> None:
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


log: structlog.stdlib.BoundLogger = structlog.get_logger()


def build_dispatcher() -> Dispatcher:
    storage = build_fsm_storage()
    dp = Dispatcher(storage=storage)
    dp.update.middleware(DbSessionMiddleware(SessionMaker))
    dp.update.middleware(UserMiddleware())
    dp.update.middleware(LangMiddleware())
    dp.include_router(build_root_router())
    return dp


async def main() -> None:
    configure_logging()
    bot = Bot(token=settings.bot_token)
    dp = build_dispatcher()

    scheduler = build_scheduler(settings.redis_url)
    scheduler.add_job(
        partial(send_due_reminders, bot=bot, session_factory=SessionMaker),
        trigger=CronTrigger(minute="*"),
        id="send_due_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        partial(expire_pending_appointments, bot=bot, session_factory=SessionMaker),
        trigger=CronTrigger(minute="*/5"),
        id="expire_pending_appointments",
        replace_existing=True,
    )

    log.info("bot_starting")
    scheduler.start()
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Прогнать гейты**

```bash
source .venv/bin/activate
pytest -q
ruff check .
ruff format --check .
mypy src/
```

Expected: зелёные. Никаких runtime-тестов на main не пишем.

- [ ] **Step 3: Смоук-тест — пересобрать контейнер и посмотреть лог**

```bash
docker compose up -d --build app
sleep 5
docker logs tg-bot-app-1 --tail 30
```

Expected:
- `"bot_starting"` в логе.
- `"Start polling"`.
- Нет стектрейсов.
- Через 1 минуту — лог APScheduler (на уровне DEBUG обычно, но main'а не ломает).

Проверить руками: создать confirmed запись через `/add`, убедиться, что в БД появились 3 строки reminders:

```bash
docker exec tg-bot-postgres-1 psql -U botik -d botik -c "SELECT kind, send_at, sent FROM reminders ORDER BY send_at;"
```

Если записей нет — проверить, что в handler'е `/add` добавлен `ReminderService` (Task 6 не пропущен).

- [ ] **Step 4: Commit**

```bash
git add src/main.py
git commit -m "feat(main): start/stop APScheduler with reminder + pending-expire jobs"
```

---

### Task 12: Переводы HY (делает пользователь)

**Files:**
- Modify: `src/strings.py` (_HY блок, только 4 ключа `REMINDER_*`)

- [ ] **Step 1: Вывести текущие HY-значения для перевода**

```bash
source .venv/bin/activate
python -c "
from src.strings import get_bundle
b = get_bundle('hy')
for key in ['REMINDER_CLIENT_DAY_BEFORE', 'REMINDER_CLIENT_TWO_HOURS',
           'REMINDER_MASTER_BEFORE', 'REMINDER_PENDING_EXPIRED']:
    print(f'{key}: {getattr(b, key)!r}')
"
```

Показать пользователю список (сейчас все — копии русских).

- [ ] **Step 2: Пользователь присылает переводы в формате `KEY: \"Armenian text\"`**

Плейсхолдеры (`{time}`, `{date}`, `{service}`, `{client_name}`, `{phone}`) **должны быть сохранены дословно**. Перевод применяется к блоку `_HY` в `src/strings.py`.

- [ ] **Step 3: Прогнать гейты**

```bash
pytest -q
ruff check .
ruff format --check .
mypy src/
```

Expected: зелёные (тест `test_strings_epic7_keys.py` продолжает проходить).

- [ ] **Step 4: Commit + тег**

```bash
git add src/strings.py
git commit -m "i18n(hy): Epic 7 translations"
git tag -a v0.7.0-epic-7 -m "Epic 7: reminders + pending expiry"
```

**Не пушить** (как и предыдущие теги — пользователь сам решит).

---

## Критерии готовности всего эпика

- [ ] Миграция `0002` применена, unique constraint активен, enum содержит `master_before`.
- [ ] При `confirm` (handler `cb_confirm`) в БД появляется 3 reminders с правильными send_at.
- [ ] При `create_manual` (handler `/add`) — то же.
- [ ] При `reject` / `cancel_by_client` — существующие reminders помечены `sent=true`.
- [ ] Job `send_due_reminders` раз в минуту шлёт сообщения и помечает sent.
- [ ] Статус-check (`appointment.status != 'confirmed'`) помечает sent без отправки.
- [ ] `TelegramBadRequest/Forbidden` помечает sent (не зациклено).
- [ ] `TelegramRetryAfter` оставляет sent=false (ретрай).
- [ ] Job `expire_pending_appointments` раз в 5 минут переводит просроченные pending в `cancelled(system)` + шлёт клиенту.
- [ ] Идемпотентность: повторный запуск не дублирует отправки.
- [ ] Все гейты зелёные: `pytest -q && ruff check . && ruff format --check . && mypy src/`.
- [ ] Ручной смоук-тест: бот запущен, `/add` → в БД reminders, лог без ошибок.
- [ ] HY-переводы применены, тег `v0.7.0-epic-7` локальный.
