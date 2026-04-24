# Epic 5 — Master Manual Booking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Команда `/add` позволяет мастеру вручную завести запись, с выбором клиента (последние 10 / поиск / новый), услуги, даты, слота (в т.ч. «нестандартное время» вне рабочих часов) и опциональным комментарием. Запись сразу `confirmed`. Клиенту с `tg_id` приходит уведомление с кнопкой «❌ Отменить запись», которая меняет `status='cancelled'` и нотифицирует мастера.

**Architecture:** Линейный FSM `MasterAdd` (9 состояний) в новом хэндлере `src/handlers/master/add_manual.py`. Переиспользуем клавиатуры и `CallbackData` из Эпика 4 (`services_pick_kb`, `calendar_keyboard`, `ClientServicePick`, `CalendarCallback`, `SlotCallback`). `BookingService.create_manual` уже существует (Эпик 3). Новые репо-методы в `ClientRepository` для recent/search. Новый сервисный метод `cancel_by_client` — обёртка над существующим `cancel`. Расширение `ApprovalCallback.action` значением `"cancel"`. Отдельный клиентский хэндлер `src/handlers/client/cancel.py`.

**Tech Stack:** Python 3.12 · aiogram 3.x · SQLAlchemy 2.0 async · PostgreSQL 16 · Redis 7 (FSM) · pytest + pytest-asyncio · ruff · mypy --strict.

**Design doc:** `docs/superpowers/specs/2026-04-21-epic-5-master-manual-booking-design.md`.

**Base branch:** `main` (Epic 4 convention). Не пушить — ждём явного разрешения пользователя.

---

## Scope sanity

Плитки работы:
1. Callback data + расширение `ApprovalCallback`
2. FSM класс
3. Repository: `list_recent_by_master`, `search_by_master`
4. Service: `cancel_by_client`
5. Keyboards: `recent_clients_kb`, `search_results_kb`, `phone_dup_kb`, `slots_grid_with_custom`, `skip_comment_kb`, `confirm_add_kb`, `client_cancel_kb`
6. Strings (Ru) — новые ключи, `_RU` only (армянский — в самом конце эпика одной задачей)
7. `ApprovalCallback("cancel")` — клиентский хэндлер `src/handlers/client/cancel.py`
8. `/add` хэндлеры (цепочка FSM), интеграция с `client_booking` (уведомление с `client_cancel_kb`)
9. Роутер-включение в `src/handlers/master/__init__.py` и `src/handlers/client/__init__.py`
10. Армянский перевод всех ключей, добавленных в Эпике 5 (ручная задача)

Всё линейно, каждая задача — один коммит. После каждой: `ruff check .`, `ruff format .`, `mypy src/`, `pytest`.

---

## Task 1: Callback data (mac/mdp/msc/mct) + ApprovalCallback "cancel"

**Files:**
- Create: `src/callback_data/master_add.py`
- Modify: `src/callback_data/approval.py`
- Test: `tests/test_callback_data_epic5.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_callback_data_epic5.py
from __future__ import annotations

from uuid import uuid4

from src.callback_data.approval import ApprovalCallback
from src.callback_data.master_add import (
    CustomTimeCallback,
    PhoneDupCallback,
    RecentClientCallback,
    SkipCommentCallback,
)


def test_recent_client_with_uuid_roundtrip() -> None:
    cid = uuid4()
    packed = RecentClientCallback(client_id=str(cid)).pack()
    assert packed.startswith("mac:")
    parsed = RecentClientCallback.unpack(packed)
    assert parsed.client_id == str(cid)


def test_recent_client_special_tokens_roundtrip() -> None:
    assert RecentClientCallback.unpack(RecentClientCallback(client_id="new").pack()).client_id == "new"
    assert (
        RecentClientCallback.unpack(RecentClientCallback(client_id="search").pack()).client_id
        == "search"
    )


def test_phone_dup_roundtrip() -> None:
    cid = uuid4()
    for action in ("use", "retry"):
        packed = PhoneDupCallback(action=action, client_id=cid).pack()  # type: ignore[arg-type]
        assert packed.startswith("mdp:")
        parsed = PhoneDupCallback.unpack(packed)
        assert parsed.action == action
        assert parsed.client_id == cid


def test_skip_comment_roundtrip() -> None:
    assert SkipCommentCallback.unpack(SkipCommentCallback().pack()).__class__ is SkipCommentCallback


def test_custom_time_roundtrip() -> None:
    assert CustomTimeCallback.unpack(CustomTimeCallback().pack()).__class__ is CustomTimeCallback


def test_approval_callback_supports_cancel() -> None:
    cid = uuid4()
    packed = ApprovalCallback(action="cancel", appointment_id=cid).pack()
    parsed = ApprovalCallback.unpack(packed)
    assert parsed.action == "cancel"
    assert parsed.appointment_id == cid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_callback_data_epic5.py -v`
Expected: FAIL — `src.callback_data.master_add` not found; `ApprovalCallback(action="cancel", ...)` fails Literal validation.

- [ ] **Step 3: Implement callback data classes**

Create `src/callback_data/master_add.py`:

```python
from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class RecentClientCallback(CallbackData, prefix="mac"):
    """Client picker: UUID string, or the sentinel 'new'/'search'."""

    client_id: str


class PhoneDupCallback(CallbackData, prefix="mdp"):
    action: Literal["use", "retry"]
    client_id: UUID


class SkipCommentCallback(CallbackData, prefix="msc"):
    pass


class CustomTimeCallback(CallbackData, prefix="mct"):
    pass
```

Modify `src/callback_data/approval.py` — add `"cancel"` to the `action` literal:

```python
from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class ApprovalCallback(CallbackData, prefix="appr"):
    action: Literal["confirm", "reject", "history", "cancel"]
    appointment_id: UUID
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `pytest tests/test_callback_data_epic5.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Quality gates**

Run: `ruff check src/callback_data/master_add.py src/callback_data/approval.py tests/test_callback_data_epic5.py && ruff format src/callback_data/master_add.py src/callback_data/approval.py tests/test_callback_data_epic5.py && mypy src/callback_data/ --strict`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/callback_data/master_add.py src/callback_data/approval.py tests/test_callback_data_epic5.py
git commit -m "feat(callbacks): Epic 5 callback data and ApprovalCallback cancel action"
```

---

## Task 2: FSM MasterAdd

**Files:**
- Create: `src/fsm/master_add.py`
- Test: `tests/test_fsm_master_add.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_fsm_master_add.py
from __future__ import annotations

from aiogram.fsm.state import State

from src.fsm.master_add import MasterAdd


def test_master_add_has_nine_states() -> None:
    states = [
        MasterAdd.PickingClient,
        MasterAdd.SearchingClient,
        MasterAdd.NewClientName,
        MasterAdd.NewClientPhone,
        MasterAdd.PickingService,
        MasterAdd.PickingDate,
        MasterAdd.PickingSlot,
        MasterAdd.EnteringCustomTime,
        MasterAdd.EnteringComment,
        MasterAdd.Confirming,
    ]
    assert len(states) == 10
    assert all(isinstance(s, State) for s in states)
```

(10 states total — `PickingClient`, `SearchingClient`, `NewClientName`, `NewClientPhone`, `PickingService`, `PickingDate`, `PickingSlot`, `EnteringCustomTime`, `EnteringComment`, `Confirming`; spec wrote "9" loosely — the concrete count is 10.)

- [ ] **Step 2: Run test**

Run: `pytest tests/test_fsm_master_add.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement FSM**

Create `src/fsm/master_add.py`:

```python
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MasterAdd(StatesGroup):
    PickingClient = State()
    SearchingClient = State()
    NewClientName = State()
    NewClientPhone = State()
    PickingService = State()
    PickingDate = State()
    PickingSlot = State()
    EnteringCustomTime = State()
    EnteringComment = State()
    Confirming = State()
```

- [ ] **Step 4: Run test — verify it passes**

Run: `pytest tests/test_fsm_master_add.py -v`
Expected: PASS.

- [ ] **Step 5: Quality gates + commit**

```bash
ruff check src/fsm/master_add.py tests/test_fsm_master_add.py && \
ruff format src/fsm/master_add.py tests/test_fsm_master_add.py && \
mypy src/fsm/ --strict && \
git add src/fsm/master_add.py tests/test_fsm_master_add.py && \
git commit -m "feat(fsm): Epic 5 MasterAdd state machine"
```

---

## Task 3: ClientRepository — list_recent_by_master, search_by_master

**Files:**
- Modify: `src/repositories/clients.py`
- Test: `tests/test_repositories_clients_epic5.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_repositories_clients_epic5.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.repositories.clients import ClientRepository


async def _master(session: AsyncSession, tg: int = 5100) -> Master:
    m = Master(tg_id=tg, name="M", timezone="Asia/Yerevan")
    session.add(m)
    await session.flush()
    return m


async def _service(session: AsyncSession, master: Master) -> Service:
    s = Service(master_id=master.id, name="Стрижка", duration_min=60)  # noqa: RUF001
    session.add(s)
    await session.flush()
    return s


async def _client(
    session: AsyncSession, master: Master, *, name: str, phone: str, created_at: datetime | None = None
) -> Client:
    c = Client(master_id=master.id, name=name, phone=phone)
    if created_at is not None:
        c.created_at = created_at
    session.add(c)
    await session.flush()
    return c


@pytest.mark.asyncio
async def test_list_recent_empty(session: AsyncSession) -> None:
    master = await _master(session)
    await session.commit()
    repo = ClientRepository(session)
    assert await repo.list_recent_by_master(master.id) == []


@pytest.mark.asyncio
async def test_list_recent_orders_by_last_appointment(session: AsyncSession) -> None:
    master = await _master(session)
    svc = await _service(session, master)
    old = await _client(session, master, name="Old", phone="+37499000001")
    recent = await _client(session, master, name="Recent", phone="+37499000002")
    no_appts = await _client(
        session, master, name="NoAppts", phone="+37499000003",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    session.add(
        Appointment(
            master_id=master.id, client_id=old.id, service_id=svc.id,
            start_at=datetime(2026, 3, 1, 10, tzinfo=UTC),
            end_at=datetime(2026, 3, 1, 11, tzinfo=UTC),
            status="confirmed", source="master_manual",
        )
    )
    session.add(
        Appointment(
            master_id=master.id, client_id=recent.id, service_id=svc.id,
            start_at=datetime(2026, 4, 15, 10, tzinfo=UTC),
            end_at=datetime(2026, 4, 15, 11, tzinfo=UTC),
            status="confirmed", source="master_manual",
        )
    )
    await session.commit()

    repo = ClientRepository(session)
    result = await repo.list_recent_by_master(master.id)
    assert [c.name for c in result] == ["Recent", "Old", "NoAppts"]


@pytest.mark.asyncio
async def test_list_recent_respects_master_scope(session: AsyncSession) -> None:
    m1 = await _master(session, tg=5201)
    m2 = await _master(session, tg=5202)
    await _client(session, m1, name="Mine", phone="+37499000011")
    await _client(session, m2, name="Other", phone="+37499000012")
    await session.commit()

    repo = ClientRepository(session)
    mine = await repo.list_recent_by_master(m1.id)
    assert [c.name for c in mine] == ["Mine"]


@pytest.mark.asyncio
async def test_list_recent_limit(session: AsyncSession) -> None:
    master = await _master(session)
    for i in range(12):
        await _client(session, master, name=f"C{i}", phone=f"+3749900{i:04d}")
    await session.commit()

    repo = ClientRepository(session)
    assert len(await repo.list_recent_by_master(master.id, limit=5)) == 5


@pytest.mark.asyncio
async def test_search_below_min_length_returns_empty(session: AsyncSession) -> None:
    master = await _master(session)
    await _client(session, master, name="Anna", phone="+37499111111")
    await session.commit()

    repo = ClientRepository(session)
    assert await repo.search_by_master(master.id, "a") == []


@pytest.mark.asyncio
async def test_search_by_name_substring(session: AsyncSession) -> None:
    master = await _master(session)
    await _client(session, master, name="Anna Karenina", phone="+37499000301")
    await _client(session, master, name="Bob", phone="+37499000302")
    await session.commit()

    repo = ClientRepository(session)
    assert [c.name for c in await repo.search_by_master(master.id, "ann")] == ["Anna Karenina"]


@pytest.mark.asyncio
async def test_search_by_phone_digits(session: AsyncSession) -> None:
    master = await _master(session)
    await _client(session, master, name="Anna", phone="+37499555111")
    await _client(session, master, name="Bob", phone="+37499999222")
    await session.commit()

    repo = ClientRepository(session)
    result = await repo.search_by_master(master.id, "555")
    assert [c.name for c in result] == ["Anna"]


@pytest.mark.asyncio
async def test_search_digits_in_raw_query_ignored(session: AsyncSession) -> None:
    master = await _master(session)
    await _client(session, master, name="Anna", phone="+37499555111")
    await session.commit()

    repo = ClientRepository(session)
    result = await repo.search_by_master(master.id, "5-5-5")
    assert [c.name for c in result] == ["Anna"]


@pytest.mark.asyncio
async def test_search_master_scope(session: AsyncSession) -> None:
    m1 = await _master(session, tg=5301)
    m2 = await _master(session, tg=5302)
    await _client(session, m1, name="Anna", phone="+37499000401")
    await _client(session, m2, name="Anna", phone="+37499000402")
    await session.commit()

    repo = ClientRepository(session)
    ids_m1 = {c.id for c in await repo.search_by_master(m1.id, "anna")}
    ids_all = {uuid4(), *ids_m1}
    assert len(ids_m1) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_repositories_clients_epic5.py -v`
Expected: FAIL — methods don't exist.

- [ ] **Step 3: Implement `list_recent_by_master` and `search_by_master`**

Modify `src/repositories/clients.py` — add imports and two methods:

```python
# at top of file: add `re` to imports
from __future__ import annotations

import re
from typing import cast
from uuid import UUID

from sqlalchemy import desc, func, nulls_last, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client
```

Append inside class `ClientRepository`:

```python
    async def list_recent_by_master(
        self, master_id: UUID, *, limit: int = 10
    ) -> list[Client]:
        """Clients ordered by their most recent appointment with this master.

        Clients without any appointments come last, ordered by `created_at DESC`.
        """
        last_appt = func.max(Appointment.start_at).label("last_appt")
        stmt = (
            select(Client)
            .outerjoin(
                Appointment,
                (Appointment.client_id == Client.id)
                & (Appointment.master_id == master_id),
            )
            .where(Client.master_id == master_id)
            .group_by(Client.id)
            .order_by(nulls_last(desc(last_appt)), desc(Client.created_at))
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())

    async def search_by_master(
        self, master_id: UUID, query: str, *, limit: int = 10
    ) -> list[Client]:
        """Substring search by name (ILIKE) and by digit-only phone.

        Queries shorter than 2 characters return an empty list. `query` is
        stripped; digits in `query` are matched against the phone stripped
        of its own non-digit characters.
        """
        q = query.strip()
        if len(q) < 2:
            return []
        digits = re.sub(r"\D", "", q)

        phone_digits = func.regexp_replace(Client.phone, r"\D", "", "g")
        like_pattern = f"%{q}%"
        digit_pattern = f"%{digits}%"

        conditions = [Client.name.ilike(like_pattern)]
        if digits:
            conditions.append(phone_digits.like(digit_pattern))

        stmt = (
            select(Client)
            .where(Client.master_id == master_id, or_(*conditions))
            .order_by(Client.name)
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())
```

- [ ] **Step 4: Run tests — verify all pass**

Run: `pytest tests/test_repositories_clients_epic5.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Quality gates + commit**

```bash
ruff check src/repositories/clients.py tests/test_repositories_clients_epic5.py && \
ruff format src/repositories/clients.py tests/test_repositories_clients_epic5.py && \
mypy src/repositories/clients.py --strict && \
git add src/repositories/clients.py tests/test_repositories_clients_epic5.py && \
git commit -m "feat(clients): Epic 5 list_recent_by_master and search_by_master"
```

---

## Task 4: BookingService.cancel_by_client

**Files:**
- Modify: `src/services/booking.py`
- Test: `tests/test_services_booking_epic5.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_services_booking_epic5.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.exceptions import InvalidState, NotFound
from src.services.booking import BookingService


async def _seed(
    session: AsyncSession, *, client_tg: int | None = 7001
) -> tuple[Master, Client, Service, Appointment]:
    master = Master(tg_id=6101, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499111111", tg_id=client_tg)  # noqa: RUF001
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)  # noqa: RUF001
    session.add(service)
    await session.flush()
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="confirmed",
        source="client_request",
    )
    session.add(appt)
    await session.flush()
    return master, client, service, appt


@pytest.mark.asyncio
async def test_cancel_by_client_happy_path(session: AsyncSession) -> None:
    master, client, service, appt = await _seed(session)
    await session.commit()

    svc = BookingService(session)
    out_appt, out_client, out_master, out_service = await svc.cancel_by_client(
        appt.id, tg_id=7001
    )
    assert out_appt.status == "cancelled"
    assert out_appt.cancelled_by == "client"
    assert out_appt.cancelled_at is not None
    assert out_client.id == client.id
    assert out_master.id == master.id
    assert out_service.id == service.id


@pytest.mark.asyncio
async def test_cancel_by_client_wrong_tg_id_raises_notfound(session: AsyncSession) -> None:
    _m, _c, _s, appt = await _seed(session)
    await session.commit()

    with pytest.raises(NotFound):
        await BookingService(session).cancel_by_client(appt.id, tg_id=9999)


@pytest.mark.asyncio
async def test_cancel_by_client_no_tg_id_on_client_raises_notfound(session: AsyncSession) -> None:
    _m, _c, _s, appt = await _seed(session, client_tg=None)
    await session.commit()

    with pytest.raises(NotFound):
        await BookingService(session).cancel_by_client(appt.id, tg_id=7001)


@pytest.mark.asyncio
async def test_cancel_by_client_missing_appointment_raises_notfound(session: AsyncSession) -> None:
    svc = BookingService(session)
    with pytest.raises(NotFound):
        await svc.cancel_by_client(uuid4(), tg_id=7001)


@pytest.mark.asyncio
async def test_cancel_by_client_already_cancelled_raises_invalid_state(
    session: AsyncSession,
) -> None:
    _m, _c, _s, appt = await _seed(session)
    appt.status = "cancelled"
    appt.cancelled_at = datetime(2026, 5, 1, tzinfo=UTC)
    appt.cancelled_by = "client"
    await session.commit()

    with pytest.raises(InvalidState):
        await BookingService(session).cancel_by_client(appt.id, tg_id=7001)
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `pytest tests/test_services_booking_epic5.py -v`
Expected: FAIL — `cancel_by_client` not defined.

- [ ] **Step 3: Implement `cancel_by_client`**

Append to class `BookingService` in `src/services/booking.py` (place the new method after `cancel`, before `create_manual`):

```python
    async def cancel_by_client(
        self,
        appointment_id: UUID,
        *,
        tg_id: int,
        now: datetime | None = None,
    ) -> tuple[Appointment, Client, Master, Service]:
        """Client-initiated cancellation. Validates ownership by `tg_id`.

        Returns (appointment, client, master, service) so the handler can build
        the master notification without additional queries. Models don't
        declare ORM `relationship()` links, so we load rows via `session.get`.
        """
        appt = await self._repo.get(appointment_id)
        if appt is None:
            raise NotFound(str(appointment_id))
        client = await self._session.get(Client, appt.client_id)
        if client is None or client.tg_id != tg_id:
            raise NotFound(str(appointment_id))
        master = await self._session.get(Master, appt.master_id)
        service = await self._session.get(Service, appt.service_id)
        if master is None or service is None:
            raise NotFound(str(appointment_id))
        await self.cancel(appointment_id, cancelled_by="client", now=now)
        return appt, client, master, service
```

No new imports needed — `Client`, `Master`, `Service`, `NotFound`, `InvalidState`, `Appointment`, `UUID`, `datetime` are already imported at the top of the file.

- [ ] **Step 4: Run tests — verify they pass**

Run: `pytest tests/test_services_booking_epic5.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Full service suite still green**

Run: `pytest tests/test_services_booking.py tests/test_services_booking_epic4.py tests/test_services_booking_epic5.py -v`
Expected: all pass.

- [ ] **Step 6: Quality gates + commit**

```bash
ruff check src/services/booking.py tests/test_services_booking_epic5.py && \
ruff format src/services/booking.py tests/test_services_booking_epic5.py && \
mypy src/services/booking.py --strict && \
git add src/services/booking.py tests/test_services_booking_epic5.py && \
git commit -m "feat(booking): Epic 5 cancel_by_client ownership-checked cancellation"
```

---

## Task 5: Keyboards (master_add)

**Files:**
- Create: `src/keyboards/master_add.py`
- Test: `tests/test_keyboards_master_add.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_keyboards_master_add.py
from __future__ import annotations

from uuid import uuid4

from src.db.models import Client
from src.keyboards.master_add import (
    client_cancel_kb,
    confirm_add_kb,
    phone_dup_kb,
    recent_clients_kb,
    search_results_kb,
    skip_comment_kb,
    slots_grid_with_custom,
)
from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def _client(name: str, phone: str) -> Client:
    c = Client(master_id=uuid4(), name=name, phone=phone)
    c.id = uuid4()
    return c


def test_recent_clients_kb_has_new_and_search_row() -> None:
    kb = recent_clients_kb([_client("Anna", "+37499111111"), _client("Bob", "+37499222222")])
    # 2 client rows + 1 trailing row with 🔍 and ➕
    assert len(kb.inline_keyboard) == 3
    last = kb.inline_keyboard[-1]
    assert len(last) == 2
    texts = [b.text for b in last]
    assert any("Поиск" in t for t in texts)  # noqa: RUF001
    assert any("Новый" in t for t in texts)


def test_recent_clients_kb_empty_just_control_row() -> None:
    kb = recent_clients_kb([])
    assert len(kb.inline_keyboard) == 1


def test_search_results_kb_has_cancel_row() -> None:
    kb = search_results_kb([_client("Anna", "+37499111111")])
    # client row + cancel search row
    assert len(kb.inline_keyboard) == 2
    assert "Отмена" in kb.inline_keyboard[-1][0].text


def test_phone_dup_kb_two_buttons() -> None:
    kb = phone_dup_kb(uuid4())
    assert len(kb.inline_keyboard) == 2
    assert all(len(row) == 1 for row in kb.inline_keyboard)


def test_slots_grid_with_custom_trailing_row() -> None:
    tz = ZoneInfo("Asia/Yerevan")
    slots = [datetime(2026, 5, 4, h, 0, tzinfo=UTC) for h in (6, 7, 8, 9)]
    kb = slots_grid_with_custom(slots, tz=tz)
    # 4 slots -> 2 rows (3+1) + 1 trailing control row
    assert len(kb.inline_keyboard) == 3
    control = kb.inline_keyboard[-1]
    assert len(control) == 2


def test_skip_comment_kb_one_button() -> None:
    kb = skip_comment_kb()
    assert len(kb.inline_keyboard) == 1
    assert len(kb.inline_keyboard[0]) == 1


def test_confirm_add_kb_two_buttons() -> None:
    kb = confirm_add_kb()
    # two buttons — implementation free to use either one row or two
    flat = [b for row in kb.inline_keyboard for b in row]
    assert len(flat) == 2


def test_client_cancel_kb_one_button() -> None:
    kb = client_cancel_kb(uuid4())
    assert len(kb.inline_keyboard) == 1
    assert len(kb.inline_keyboard[0]) == 1
```

- [ ] **Step 2: Run test — verify fail**

Run: `pytest tests/test_keyboards_master_add.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement keyboards**

Create `src/keyboards/master_add.py`:

```python
from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.approval import ApprovalCallback
from src.callback_data.master_add import (
    CustomTimeCallback,
    PhoneDupCallback,
    RecentClientCallback,
    SkipCommentCallback,
)
from src.callback_data.slots import SlotCallback
from src.db.models import Client
from src.strings import strings


def _client_button(client: Client) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=f"{client.name} · {client.phone}",
        callback_data=RecentClientCallback(client_id=str(client.id)).pack(),
    )


def _control_row_for_picker() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=strings.MANUAL_BTN_SEARCH,
            callback_data=RecentClientCallback(client_id="search").pack(),
        ),
        InlineKeyboardButton(
            text=strings.MANUAL_BTN_NEW,
            callback_data=RecentClientCallback(client_id="new").pack(),
        ),
    ]


def recent_clients_kb(clients: list[Client]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [[_client_button(c)] for c in clients]
    rows.append(_control_row_for_picker())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_results_kb(clients: list[Client]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [[_client_button(c)] for c in clients]
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.MANUAL_BTN_SEARCH_CANCEL,
                callback_data="master_add_search_cancel",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def phone_dup_kb(client_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.MANUAL_BTN_DUP_USE,
                    callback_data=PhoneDupCallback(action="use", client_id=client_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.MANUAL_BTN_DUP_RETRY,
                    callback_data=PhoneDupCallback(action="retry", client_id=client_id).pack(),
                )
            ],
        ]
    )


def slots_grid_with_custom(
    slots: list[datetime], *, tz: ZoneInfo
) -> InlineKeyboardMarkup:
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
        [
            InlineKeyboardButton(
                text=strings.MANUAL_BTN_CUSTOM_TIME,
                callback_data=CustomTimeCallback().pack(),
            ),
            InlineKeyboardButton(
                text=strings.MANUAL_BTN_BACK,
                callback_data="master_add_back",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_comment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.MANUAL_BTN_SKIP,
                    callback_data=SkipCommentCallback().pack(),
                )
            ]
        ]
    )


def confirm_add_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.MANUAL_BTN_SAVE,
                    callback_data="master_add_save",
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.MANUAL_BTN_CANCEL,
                    callback_data="master_add_cancel",
                )
            ],
        ]
    )


def client_cancel_kb(appointment_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.CLIENT_CANCEL_BUTTON,
                    callback_data=ApprovalCallback(
                        action="cancel", appointment_id=appointment_id
                    ).pack(),
                )
            ]
        ]
    )
```

- [ ] **Step 4: Run test — verify pass**

Run: `pytest tests/test_keyboards_master_add.py -v`
Expected: FAIL (because strings don't yet have the new keys). This is expected — Task 6 introduces them. Proceed to Task 6; after Task 6 the keyboard tests will pass.

**Gate:** do not commit Task 5 yet — commit after Task 6 together, since the keyboards depend on strings that don't exist until Task 6. Stage both in the same commit.

---

## Task 6: Strings (Ru) + combined commit for Tasks 5+6

**Files:**
- Modify: `src/strings.py`

- [ ] **Step 1: Add Russian keys to `_RU` in `src/strings.py`**

Locate the `_RU: dict[str, str] = { ... }` literal. Insert after the last existing key and before the closing brace:

```python
    # --- Epic 5: master manual add ---
    "MANUAL_PICK_CLIENT": "Выбери клиента или создай нового:",
    "MANUAL_NO_RECENT": "Ещё нет клиентов. Нажми ➕ Новый.",
    "MANUAL_SEARCH_PROMPT": "Введи 2+ символа (имя или телефон):",
    "MANUAL_SEARCH_EMPTY": "Ничего не нашёл. Попробуй ещё.",
    "MANUAL_ASK_NAME": "Имя клиента:",
    "MANUAL_NAME_BAD": "Минимум 2 символа. Попробуй ещё.",
    "MANUAL_ASK_PHONE": "Телефон клиента (+374XXXXXXXX):",
    "MANUAL_PHONE_BAD": "Формат: +374XXXXXXXX. Попробуй ещё.",
    "MANUAL_PHONE_DUP": "По этому номеру уже есть клиент «{name}». Использовать его?",
    "MANUAL_ASK_SERVICE": "Выбери услугу:",
    "MANUAL_ASK_DATE": "Выбери дату:",
    "MANUAL_ASK_SLOT": "Выбери время или введи нестандартное:",
    "MANUAL_CUSTOM_PROMPT": "Введи дату и время: ДД.ММ ЧЧ:ММ (или только ЧЧ:ММ для выбранной даты):",
    "MANUAL_CUSTOM_BAD": "Неверный формат. Пример: 25.04 14:30",
    "MANUAL_CUSTOM_PAST": "Нельзя в прошлое. Выбери другое время.",
    "MANUAL_ASK_COMMENT": "Комментарий (или нажми ⏭ Пропустить):",
    "MANUAL_CONFIRM_CARD": "Подтверди запись:\n👤 {client}\n📞 {phone}\n💇 {service}\n📅 {date} {time}\n📝 {notes}",
    "MANUAL_SAVED": "✅ Запись сохранена.",
    "MANUAL_CANCELED": "Отменено.",
    "MANUAL_SLOT_TAKEN": "Этот слот только что занят. Выбери другой.",
    "MANUAL_BTN_SEARCH": "🔍 Поиск",
    "MANUAL_BTN_NEW": "➕ Новый",
    "MANUAL_BTN_SEARCH_CANCEL": "⬅ Отмена поиска",
    "MANUAL_BTN_DUP_USE": "Да, использовать",
    "MANUAL_BTN_DUP_RETRY": "Отмена — ввести другой",
    "MANUAL_BTN_CUSTOM_TIME": "➕ Нестандартное время",
    "MANUAL_BTN_BACK": "⬅ Назад",
    "MANUAL_BTN_SKIP": "⏭ Пропустить",
    "MANUAL_BTN_SAVE": "✅ Сохранить",
    "MANUAL_BTN_CANCEL": "❌ Отмена",
    # --- client-side cancellation + notification ---
    "CLIENT_NOTIFY_MANUAL": "Врач записал вас на {date} {time} — {service}.",
    "CLIENT_CANCEL_BUTTON": "❌ Отменить запись",
    "CLIENT_CANCEL_DONE": "Запись отменена.",
    "CLIENT_CANCEL_UNAVAILABLE": "Запись уже недоступна.",
    "MASTER_NOTIFY_CLIENT_CANCELED": "Клиент {name} отменил запись: {date} {time} — {service}.",
```

- [ ] **Step 2: Mirror same keys in `_HY`** — with the **same Russian values** for now (армянский перевод — отдельной задачей в конце эпика; пока русский fallback, чтобы не падало на `lang=hy`).

Insert the same block inside the `_HY: dict[str, str] = { ... }` literal.

- [ ] **Step 3: Run keyboard tests — they should pass now**

Run: `pytest tests/test_keyboards_master_add.py -v`
Expected: PASS (8 tests).

- [ ] **Step 4: Full suite still green**

Run: `pytest -v`
Expected: all pass (152 existing + 9 repo + 5 service + 5 callback + 1 FSM + 8 keyboards = 180 tests).

- [ ] **Step 5: Quality gates + combined commit (Tasks 5+6)**

```bash
ruff check . && ruff format --check . && mypy src/ --strict && \
git add src/keyboards/master_add.py src/strings.py tests/test_keyboards_master_add.py && \
git commit -m "feat(keyboards,strings): Epic 5 master_add keyboards + RU strings"
```

---

## Task 7: Client-side cancel handler

**Files:**
- Create: `src/handlers/client/cancel.py`
- Modify: `src/handlers/client/__init__.py`
- Test: `tests/test_handlers_client_cancel.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_handlers_client_cancel.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.approval import ApprovalCallback
from src.db.models import Appointment, Client, Master, Service
from src.handlers.client.cancel import handle_cancel


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMsg:
    edited_markup: bool = False

    async def edit_reply_markup(self, *, reply_markup: Any = None) -> None:
        self.edited_markup = True


@dataclass
class _FakeCb:
    from_user: _FakeUser
    message: _FakeMsg = field(default_factory=_FakeMsg)
    answered: list[tuple[str, bool]] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append((text, show_alert))


async def _seed(session: AsyncSession, *, client_tg: int | None = 9001) -> Appointment:
    master = Master(tg_id=9100, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499111111", tg_id=client_tg)  # noqa: RUF001
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)  # noqa: RUF001
    session.add(service)
    await session.flush()
    appt = Appointment(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="confirmed", source="master_manual",
    )
    session.add(appt)
    await session.flush()
    await session.commit()
    return appt


@pytest.mark.asyncio
async def test_cancel_happy_path_notifies_master(session: AsyncSession) -> None:
    appt = await _seed(session)
    bot = AsyncMock()
    cb = _FakeCb(from_user=_FakeUser(id=9001))

    await handle_cancel(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ApprovalCallback(action="cancel", appointment_id=appt.id),
        session=session,
        bot=bot,
    )
    bot.send_message.assert_awaited_once()
    assert cb.message.edited_markup is True
    assert cb.answered  # at least one answer call
    # The bot.send_message kwargs should carry a chat_id matching master tg
    _, kwargs = bot.send_message.call_args
    assert kwargs["chat_id"] == 9100


@pytest.mark.asyncio
async def test_cancel_wrong_tg_alerts_unavailable(session: AsyncSession) -> None:
    appt = await _seed(session)
    bot = AsyncMock()
    cb = _FakeCb(from_user=_FakeUser(id=12345))

    await handle_cancel(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ApprovalCallback(action="cancel", appointment_id=appt.id),
        session=session,
        bot=bot,
    )
    bot.send_message.assert_not_awaited()
    # alert was raised
    assert any(show for _, show in cb.answered)


@pytest.mark.asyncio
async def test_cancel_missing_appt_alerts_unavailable(session: AsyncSession) -> None:
    bot = AsyncMock()
    cb = _FakeCb(from_user=_FakeUser(id=9001))

    await handle_cancel(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ApprovalCallback(action="cancel", appointment_id=uuid4()),
        session=session,
        bot=bot,
    )
    bot.send_message.assert_not_awaited()
    assert any(show for _, show in cb.answered)
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_handlers_client_cancel.py -v`
Expected: FAIL — `src.handlers.client.cancel` missing.

- [ ] **Step 3: Implement the handler**

Create `src/handlers/client/cancel.py`:

```python
from __future__ import annotations

from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.approval import ApprovalCallback
from src.exceptions import InvalidState, NotFound
from src.services.booking import BookingService
from src.strings import strings

router = Router(name="client_cancel")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


@router.callback_query(ApprovalCallback.filter(F.action == "cancel"))
async def handle_cancel(
    callback: CallbackQuery,
    callback_data: ApprovalCallback,
    session: AsyncSession,
    bot: Bot,
) -> None:
    tg_id = callback.from_user.id if callback.from_user else 0
    svc = BookingService(session)
    try:
        appt, client, master, service = await svc.cancel_by_client(
            callback_data.appointment_id, tg_id=tg_id
        )
    except (NotFound, InvalidState):
        await callback.answer(strings.CLIENT_CANCEL_UNAVAILABLE, show_alert=True)
        return
    await session.commit()

    await callback.answer(strings.CLIENT_CANCEL_DONE)
    if callback.message is not None and hasattr(callback.message, "edit_reply_markup"):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:  # noqa: BLE001
            log.warning("cancel_kb_strip_failed", appointment_id=str(appt.id))

    tz = ZoneInfo(master.timezone)
    local = appt.start_at.astimezone(tz)
    text = strings.MASTER_NOTIFY_CLIENT_CANCELED.format(
        name=client.name,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        service=service.name,
    )
    try:
        await bot.send_message(chat_id=master.tg_id, text=text)
    except Exception:  # noqa: BLE001
        log.warning("master_notify_failed", master_tg=master.tg_id)
    log.info("client_cancelled", appointment_id=str(appt.id), client_tg=tg_id)
```

Modify `src/handlers/client/__init__.py` — include new router:

```python
from __future__ import annotations

from aiogram import Router

from src.handlers.client.booking import router as booking_router
from src.handlers.client.cancel import router as cancel_router
from src.handlers.client.start import router as start_router

router = Router(name="client")
router.include_router(start_router)
router.include_router(booking_router)
router.include_router(cancel_router)

__all__ = ["router"]
```

- [ ] **Step 4: Run tests — verify pass**

Run: `pytest tests/test_handlers_client_cancel.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Quality gates + commit**

```bash
ruff check src/handlers/client/ tests/test_handlers_client_cancel.py && \
ruff format src/handlers/client/ tests/test_handlers_client_cancel.py && \
mypy src/handlers/client/ --strict && \
git add src/handlers/client/cancel.py src/handlers/client/__init__.py tests/test_handlers_client_cancel.py && \
git commit -m "feat(client): Epic 5 client-initiated cancellation handler"
```

---

## Task 8: /add handler — part A (entry → client picker → new/existing → service)

**Files:**
- Create: `src/handlers/master/add_manual.py`
- Test: `tests/test_handlers_master_add_part_a.py`

**Note:** This task covers `cmd_add` through `cb_pick_service`. The slot/time/comment/confirm steps live in Task 9. Split to keep reviews tractable.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_handlers_master_add_part_a.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.client_services import ClientServicePick
from src.callback_data.master_add import PhoneDupCallback, RecentClientCallback
from src.db.models import Client, Master, Service
from src.fsm.master_add import MasterAdd
from src.handlers.master.add_manual import (
    cb_phone_dup,
    cb_pick_recent,
    cb_pick_service,
    cmd_add,
    msg_new_client_name,
    msg_new_client_phone,
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
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed_master(session: AsyncSession) -> Master:
    m = Master(tg_id=5500, name="M", timezone="Asia/Yerevan")
    session.add(m)
    await session.flush()
    await session.commit()
    return m


@pytest.mark.asyncio
async def test_cmd_add_empty_state_shows_no_recent_hint(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))
    await cmd_add(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterAdd.PickingClient.state
    # No clients yet — hint text + keyboard with only control row
    assert msg.answers


@pytest.mark.asyncio
async def test_cb_pick_recent_new_transitions_to_name(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.PickingClient)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_pick_recent(
        callback=cb,  # type: ignore[arg-type]
        callback_data=RecentClientCallback(client_id="new"),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.NewClientName.state


@pytest.mark.asyncio
async def test_cb_pick_recent_search_transitions_to_search(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.PickingClient)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_pick_recent(
        callback=cb,  # type: ignore[arg-type]
        callback_data=RecentClientCallback(client_id="search"),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.SearchingClient.state


@pytest.mark.asyncio
async def test_cb_pick_recent_existing_goes_to_service_pick(session: AsyncSession) -> None:
    master = await _seed_master(session)
    client = Client(master_id=master.id, name="Анна", phone="+37499111111")  # noqa: RUF001
    session.add(client)
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)  # noqa: RUF001
    session.add(svc)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterAdd.PickingClient)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_pick_recent(
        callback=cb,  # type: ignore[arg-type]
        callback_data=RecentClientCallback(client_id=str(client.id)),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.PickingService.state
    assert (await state.get_data())["client_id"] == str(client.id)


@pytest.mark.asyncio
async def test_msg_search_below_min_length_keeps_state(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.SearchingClient)
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="a")
    await msg_search_query(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterAdd.SearchingClient.state


@pytest.mark.asyncio
async def test_msg_new_client_name_too_short_keeps_state(session: AsyncSession) -> None:
    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientName)
    msg = _FakeMsg(text="A")
    await msg_new_client_name(message=msg, state=state)
    assert await state.get_state() == MasterAdd.NewClientName.state


@pytest.mark.asyncio
async def test_msg_new_client_name_ok_advances(session: AsyncSession) -> None:
    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientName)
    msg = _FakeMsg(text="Борис")  # noqa: RUF001
    await msg_new_client_name(message=msg, state=state)
    assert await state.get_state() == MasterAdd.NewClientPhone.state
    assert (await state.get_data())["pending_name"] == "Борис"  # noqa: RUF001


@pytest.mark.asyncio
async def test_msg_new_client_phone_fresh_creates_and_advances(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientPhone)
    await state.update_data(pending_name="Борис")  # noqa: RUF001
    msg = _FakeMsg(text="+374991122333")  # correct length example below
    # Fix: +37499112233 (8 national digits)
    msg.text = "+37499112233"
    await msg_new_client_phone(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterAdd.PickingService.state
    data = await state.get_data()
    assert "client_id" in data


@pytest.mark.asyncio
async def test_msg_new_client_phone_dup_waits_for_decision(session: AsyncSession) -> None:
    master = await _seed_master(session)
    existing = Client(master_id=master.id, name="Анна", phone="+37499500500")  # noqa: RUF001
    session.add(existing)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientPhone)
    await state.update_data(pending_name="Аня")  # noqa: RUF001
    msg = _FakeMsg(text="+37499500500")
    await msg_new_client_phone(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterAdd.NewClientPhone.state
    assert (await state.get_data())["pending_phone"] == "+37499500500"


@pytest.mark.asyncio
async def test_cb_phone_dup_use_advances(session: AsyncSession) -> None:
    master = await _seed_master(session)
    existing = Client(master_id=master.id, name="Анна", phone="+37499500500")  # noqa: RUF001
    session.add(existing)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientPhone)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_phone_dup(
        callback=cb,  # type: ignore[arg-type]
        callback_data=PhoneDupCallback(action="use", client_id=existing.id),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.PickingService.state
    assert (await state.get_data())["client_id"] == str(existing.id)


@pytest.mark.asyncio
async def test_cb_phone_dup_retry_prompts_again(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientPhone)
    await state.update_data(pending_name="Аня", pending_phone="+37499500500")  # noqa: RUF001
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_phone_dup(
        callback=cb,  # type: ignore[arg-type]
        callback_data=PhoneDupCallback(action="retry", client_id=uuid4()),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.NewClientPhone.state
    data = await state.get_data()
    assert "pending_phone" not in data


@pytest.mark.asyncio
async def test_cb_pick_service_advances_to_date(session: AsyncSession) -> None:
    master = Master(
        tg_id=5600, name="M", timezone="Asia/Yerevan",
        work_hours={"mon": [["10:00", "19:00"]]},
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499000700")  # noqa: RUF001
    session.add(client)
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)  # noqa: RUF001
    session.add(svc)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterAdd.PickingService)
    await state.update_data(client_id=str(client.id))
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_pick_service(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientServicePick(service_id=svc.id),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.PickingDate.state
    assert (await state.get_data())["service_id"] == str(svc.id)
```

- [ ] **Step 2: Run — verify fail (module missing)**

Run: `pytest tests/test_handlers_master_add_part_a.py -v`
Expected: FAIL — handlers don't exist.

- [ ] **Step 3: Implement Part A of `add_manual.py`**

Create `src/handlers/master/add_manual.py`:

```python
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.calendar import CalendarCallback
from src.callback_data.client_services import ClientServicePick
from src.callback_data.master_add import (
    PhoneDupCallback,
    RecentClientCallback,
)
from src.db.models import Client, Master
from src.fsm.master_add import MasterAdd
from src.keyboards.calendar import calendar_keyboard
from src.keyboards.master_add import phone_dup_kb, recent_clients_kb, search_results_kb
from src.keyboards.slots import services_pick_kb
from src.repositories.clients import ClientRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.strings import strings
from src.utils.phone import normalize as normalize_phone
from src.utils.time import now_utc

router = Router(name="master_add_manual")
log: structlog.stdlib.BoundLogger = structlog.get_logger()

_MIN_NAME = 2
_MIN_SEARCH = 2


@router.message(Command("add"))
async def cmd_add(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    repo = ClientRepository(session)
    clients = await repo.list_recent_by_master(master.id)
    text = strings.MANUAL_PICK_CLIENT if clients else strings.MANUAL_NO_RECENT
    await state.clear()
    await state.set_state(MasterAdd.PickingClient)
    await message.answer(text, reply_markup=recent_clients_kb(clients))


@router.callback_query(RecentClientCallback.filter(), MasterAdd.PickingClient)
@router.callback_query(RecentClientCallback.filter(), MasterAdd.SearchingClient)
async def cb_pick_recent(
    callback: CallbackQuery,
    callback_data: RecentClientCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    if callback_data.client_id == "new":
        await state.set_state(MasterAdd.NewClientName)
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(strings.MANUAL_ASK_NAME)
        return
    if callback_data.client_id == "search":
        await state.set_state(MasterAdd.SearchingClient)
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(strings.MANUAL_SEARCH_PROMPT)
        return

    # Concrete UUID
    try:
        picked_id = UUID(callback_data.client_id)
    except ValueError:
        await callback.answer("Bad id", show_alert=True)
        return
    await state.update_data(client_id=str(picked_id))
    await _show_services(state, session, master, reply_to=callback.message)


async def _show_services(
    state: FSMContext, session: AsyncSession, master: Master, *, reply_to: Any
) -> None:
    services = await ServiceRepository(session).list_active(master_id=master.id)
    await state.set_state(MasterAdd.PickingService)
    if reply_to is not None and hasattr(reply_to, "answer"):
        await reply_to.answer(
            strings.MANUAL_ASK_SERVICE, reply_markup=services_pick_kb(services)
        )


@router.message(MasterAdd.SearchingClient)
async def msg_search_query(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    q = (message.text or "").strip()
    if len(q) < _MIN_SEARCH:
        await message.answer(strings.MANUAL_SEARCH_PROMPT)
        return
    repo = ClientRepository(session)
    results = await repo.search_by_master(master.id, q)
    if not results:
        await message.answer(strings.MANUAL_SEARCH_EMPTY)
        return
    await message.answer(
        strings.MANUAL_PICK_CLIENT, reply_markup=search_results_kb(results)
    )


@router.callback_query(F.data == "master_add_search_cancel", MasterAdd.SearchingClient)
async def cb_search_cancel(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, master: Master
) -> None:
    await callback.answer()
    repo = ClientRepository(session)
    clients = await repo.list_recent_by_master(master.id)
    await state.set_state(MasterAdd.PickingClient)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_PICK_CLIENT, reply_markup=recent_clients_kb(clients)
        )


@router.message(MasterAdd.NewClientName)
async def msg_new_client_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < _MIN_NAME:
        await message.answer(strings.MANUAL_NAME_BAD)
        return
    await state.update_data(pending_name=name)
    await state.set_state(MasterAdd.NewClientPhone)
    await message.answer(strings.MANUAL_ASK_PHONE)


@router.message(MasterAdd.NewClientPhone)
async def msg_new_client_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    raw = (message.text or "").strip()
    normalized = normalize_phone(raw)
    if normalized is None:
        await message.answer(strings.MANUAL_PHONE_BAD)
        return
    data = await state.get_data()
    name = data.get("pending_name", "")
    repo = ClientRepository(session)
    # Check for existing (master_id, phone)
    from sqlalchemy import select  # local import to keep file imports focused

    existing = await session.scalar(
        select(Client).where(Client.master_id == master.id, Client.phone == normalized)
    )
    if existing is not None:
        await state.update_data(pending_phone=normalized)
        await message.answer(
            strings.MANUAL_PHONE_DUP.format(name=existing.name),
            reply_markup=phone_dup_kb(existing.id),
        )
        return
    created = await repo.upsert_by_phone(
        master_id=master.id, phone=normalized, name=name, tg_id=None
    )
    await session.commit()
    await state.update_data(client_id=str(created.id))
    await state.set_state(MasterAdd.PickingService)
    await _show_services(state, session, master, reply_to=message)


@router.callback_query(PhoneDupCallback.filter(), MasterAdd.NewClientPhone)
async def cb_phone_dup(
    callback: CallbackQuery,
    callback_data: PhoneDupCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    if callback_data.action == "use":
        await state.update_data(client_id=str(callback_data.client_id))
        await _show_services(state, session, master, reply_to=callback.message)
        return
    # retry: drop pending_phone, prompt again
    data = await state.get_data()
    data.pop("pending_phone", None)
    await state.set_data(data)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.MANUAL_ASK_PHONE)


@router.callback_query(ClientServicePick.filter(), MasterAdd.PickingService)
async def cb_pick_service(
    callback: CallbackQuery,
    callback_data: ClientServicePick,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    s_repo = ServiceRepository(session)
    service = await s_repo.get(callback_data.service_id, master_id=master.id)
    if service is None:
        await callback.answer("Service missing", show_alert=True)
        return
    await state.update_data(service_id=str(service.id))
    await state.set_state(MasterAdd.PickingDate)

    tz = ZoneInfo(master.timezone)
    today = now_utc().astimezone(tz).date()
    month = today.replace(day=1)
    loads = await BookingService(session).get_month_load(
        master=master, service=service, month=month, now=now_utc()
    )
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_ASK_DATE,
            reply_markup=calendar_keyboard(month=month, loads=loads, today=today),
        )
```

**Note:** `ServiceRepository.list_active` — confirm method name by reading `src/repositories/services.py` first. If the existing method is named differently, adjust the call. Implementer must verify before coding.

- [ ] **Step 4: Run Part A tests**

Run: `pytest tests/test_handlers_master_add_part_a.py -v`
Expected: all 12 tests pass.

- [ ] **Step 5: Full suite still green**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 6: Quality gates + commit**

```bash
ruff check src/handlers/master/add_manual.py tests/test_handlers_master_add_part_a.py && \
ruff format src/handlers/master/add_manual.py tests/test_handlers_master_add_part_a.py && \
mypy src/handlers/master/add_manual.py --strict && \
git add src/handlers/master/add_manual.py tests/test_handlers_master_add_part_a.py && \
git commit -m "feat(master): Epic 5 /add handler part A — client picker and service"
```

---

## Task 9: /add handler — part B (date → slot → custom → comment → confirm → save)

**Files:**
- Modify: `src/handlers/master/add_manual.py`
- Modify: `src/handlers/master/__init__.py`
- Test: `tests/test_handlers_master_add_part_b.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_handlers_master_add_part_b.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.calendar import CalendarCallback
from src.callback_data.master_add import CustomTimeCallback, SkipCommentCallback
from src.callback_data.slots import SlotCallback
from src.db.models import Client, Master, Service
from src.fsm.master_add import MasterAdd
from src.handlers.master.add_manual import (
    cb_confirm_cancel,
    cb_confirm_save,
    cb_custom_time,
    cb_pick_date,
    cb_pick_slot,
    cb_skip_comment,
    cmd_cancel_any,
    msg_comment,
    msg_custom_time,
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
    answered: list[tuple[str, bool]] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append((text, show_alert))


async def _mkctx() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=6200, name="M", timezone="Asia/Yerevan",
        work_hours={
            "mon": [["10:00", "19:00"]], "tue": [["10:00", "19:00"]],
            "wed": [["10:00", "19:00"]], "thu": [["10:00", "19:00"]],
            "fri": [["10:00", "19:00"]], "sat": [["10:00", "19:00"]],
            "sun": [["10:00", "19:00"]],
        },
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499200200", tg_id=None)  # noqa: RUF001
    session.add(client)
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)  # noqa: RUF001
    session.add(svc)
    await session.flush()
    await session.commit()
    return master, client, svc


@pytest.mark.asyncio
async def test_cb_pick_slot_advances_to_comment(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.PickingSlot)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        date=date(2026, 5, 4).isoformat(),
    )
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_pick_slot(
        callback=cb,  # type: ignore[arg-type]
        callback_data=SlotCallback(hour=11, minute=0),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.EnteringComment.state
    data = await state.get_data()
    assert "start_at" in data


@pytest.mark.asyncio
async def test_cb_custom_time_enters_custom_state(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.PickingSlot)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        date=date(2026, 5, 4).isoformat(),
    )
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_custom_time(
        callback=cb,  # type: ignore[arg-type]
        callback_data=CustomTimeCallback(),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.EnteringCustomTime.state


@pytest.mark.asyncio
async def test_msg_custom_time_bad_format_stays(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.EnteringCustomTime)
    await state.update_data(date=date(2026, 5, 4).isoformat())
    msg = _FakeMsg(text="завтра вечером")  # noqa: RUF001
    await msg_custom_time(message=msg, state=state, master=master)
    assert await state.get_state() == MasterAdd.EnteringCustomTime.state


@pytest.mark.asyncio
async def test_msg_custom_time_past_rejected(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.EnteringCustomTime)
    await state.update_data(date=date(2020, 1, 1).isoformat())
    msg = _FakeMsg(text="10:00")
    await msg_custom_time(message=msg, state=state, master=master)
    assert await state.get_state() == MasterAdd.EnteringCustomTime.state


@pytest.mark.asyncio
async def test_msg_custom_time_ok_advances(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.EnteringCustomTime)
    # Pick a date in 2030 so it's always in the future for test determinism.
    await state.update_data(date=date(2030, 6, 1).isoformat())
    msg = _FakeMsg(text="25.06 14:30")
    await msg_custom_time(message=msg, state=state, master=master)
    assert await state.get_state() == MasterAdd.EnteringComment.state


@pytest.mark.asyncio
async def test_msg_comment_advances_to_confirming(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.EnteringComment)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        start_at=datetime(2030, 6, 25, 10, 30, tzinfo=UTC).isoformat(),
    )
    msg = _FakeMsg(text="Принести шампунь")  # noqa: RUF001
    await msg_comment(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterAdd.Confirming.state
    assert (await state.get_data())["comment"] == "Принести шампунь"  # noqa: RUF001


@pytest.mark.asyncio
async def test_cb_skip_comment_advances_to_confirming(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.EnteringComment)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        start_at=datetime(2030, 6, 25, 10, 30, tzinfo=UTC).isoformat(),
    )
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_skip_comment(
        callback=cb,  # type: ignore[arg-type]
        callback_data=SkipCommentCallback(),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.Confirming.state
    assert (await state.get_data())["comment"] is None


@pytest.mark.asyncio
async def test_cb_confirm_save_creates_appointment_clears_state(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.Confirming)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        start_at=datetime(2030, 6, 25, 10, 30, tzinfo=UTC).isoformat(),
        comment=None,
    )
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    bot = AsyncMock()
    await cb_confirm_save(
        callback=cb,  # type: ignore[arg-type]
        state=state,
        session=session,
        master=master,
        bot=bot,
    )
    assert await state.get_state() is None  # cleared
    # client has no tg_id -> no notification
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_cb_confirm_save_notifies_client_when_tg_present(session: AsyncSession) -> None:
    master = Master(
        tg_id=6201, name="M", timezone="Asia/Yerevan",
        work_hours={"mon": [["10:00", "19:00"]]},
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Борис", phone="+37499300300", tg_id=77777)  # noqa: RUF001
    session.add(client)
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)  # noqa: RUF001
    session.add(svc)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterAdd.Confirming)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        start_at=datetime(2030, 6, 25, 10, 30, tzinfo=UTC).isoformat(),
        comment=None,
    )
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    bot = AsyncMock()
    await cb_confirm_save(
        callback=cb,  # type: ignore[arg-type]
        state=state,
        session=session,
        master=master,
        bot=bot,
    )
    bot.send_message.assert_awaited_once()
    _, kwargs = bot.send_message.call_args
    assert kwargs["chat_id"] == 77777


@pytest.mark.asyncio
async def test_cb_confirm_cancel_clears_state(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.Confirming)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_confirm_cancel(callback=cb, state=state)  # type: ignore[arg-type]
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_cmd_cancel_any_clears_state(session: AsyncSession) -> None:
    state = await _mkctx()
    await state.set_state(MasterAdd.PickingService)
    msg = _FakeMsg()
    await cmd_cancel_any(message=msg, state=state)
    assert await state.get_state() is None
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_handlers_master_add_part_b.py -v`
Expected: FAIL — handlers missing.

- [ ] **Step 3: Implement Part B**

Append to `src/handlers/master/add_manual.py`:

```python
# --- Part B: date/slot/custom/comment/confirm ---

import re as _re  # keep grouped with other imports at top when implementing
from datetime import UTC, datetime, timedelta
from aiogram import Bot
from aiogram.filters import Command
from src.callback_data.master_add import CustomTimeCallback, SkipCommentCallback
from src.callback_data.slots import SlotCallback
from src.db.models import Service
from src.exceptions import SlotAlreadyTaken
from src.keyboards.master_add import (
    client_cancel_kb,
    confirm_add_kb,
    skip_comment_kb,
    slots_grid_with_custom,
)
from src.repositories.masters import MasterRepository  # noqa: F401 reserved for future
from src.services.booking import BookingService
from src.utils.phone import normalize as _normalize_phone  # already imported — de-dupe

_CUSTOM_FULL_RE = _re.compile(r"^(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})$")
_CUSTOM_TIME_RE = _re.compile(r"^(\d{1,2}):(\d{2})$")
_COMMENT_MAX = 200


@router.callback_query(CalendarCallback.filter(), MasterAdd.PickingDate)
async def cb_pick_date(
    callback: CallbackQuery,
    callback_data: CalendarCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    if callback_data.action == "noop":
        return

    data = await state.get_data()
    service_id = UUID(data["service_id"])
    service = await ServiceRepository(session).get(service_id, master_id=master.id)
    if service is None:
        await state.clear()
        return

    tz = ZoneInfo(master.timezone)
    today = now_utc().astimezone(tz).date()
    svc = BookingService(session)

    if callback_data.action == "nav":
        month = date(callback_data.year, callback_data.month, 1)
        loads = await svc.get_month_load(master=master, service=service, month=month, now=now_utc())
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(
                strings.MANUAL_ASK_DATE,
                reply_markup=calendar_keyboard(month=month, loads=loads, today=today),
            )
        return

    # pick
    picked = date(callback_data.year, callback_data.month, callback_data.day)
    slots = await svc.get_free_slots(master, service, picked, now=now_utc())
    await state.update_data(date=picked.isoformat())
    await state.set_state(MasterAdd.PickingSlot)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_ASK_SLOT, reply_markup=slots_grid_with_custom(slots, tz=tz)
        )


@router.callback_query(SlotCallback.filter(), MasterAdd.PickingSlot)
async def cb_pick_slot(
    callback: CallbackQuery,
    callback_data: SlotCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    data = await state.get_data()
    picked = date.fromisoformat(data["date"])
    tz = ZoneInfo(master.timezone)
    local_start = datetime(
        picked.year, picked.month, picked.day, callback_data.hour, callback_data.minute, tzinfo=tz
    )
    start_at_utc = local_start.astimezone(UTC)
    await state.update_data(start_at=start_at_utc.isoformat())
    await state.set_state(MasterAdd.EnteringComment)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.MANUAL_ASK_COMMENT, reply_markup=skip_comment_kb())


@router.callback_query(CustomTimeCallback.filter(), MasterAdd.PickingSlot)
async def cb_custom_time(
    callback: CallbackQuery,
    callback_data: CustomTimeCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    await state.set_state(MasterAdd.EnteringCustomTime)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.MANUAL_CUSTOM_PROMPT)


@router.callback_query(F.data == "master_add_back", MasterAdd.PickingSlot)
async def cb_back_to_date(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, master: Master
) -> None:
    await callback.answer()
    data = await state.get_data()
    service_id = UUID(data["service_id"])
    service = await ServiceRepository(session).get(service_id, master_id=master.id)
    if service is None:
        await state.clear()
        return
    tz = ZoneInfo(master.timezone)
    today = now_utc().astimezone(tz).date()
    month = today.replace(day=1)
    loads = await BookingService(session).get_month_load(
        master=master, service=service, month=month, now=now_utc()
    )
    await state.set_state(MasterAdd.PickingDate)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_ASK_DATE,
            reply_markup=calendar_keyboard(month=month, loads=loads, today=today),
        )


@router.message(MasterAdd.EnteringCustomTime)
async def msg_custom_time(
    message: Message,
    state: FSMContext,
    master: Master,
) -> None:
    raw = (message.text or "").strip()
    tz = ZoneInfo(master.timezone)
    data = await state.get_data()
    current_date = date.fromisoformat(data["date"]) if data.get("date") else None

    m_full = _CUSTOM_FULL_RE.match(raw)
    m_time = _CUSTOM_TIME_RE.match(raw)

    if m_full:
        dd, mm, hh, mi = (int(g) for g in m_full.groups())
        today = now_utc().astimezone(tz).date()
        year = today.year
        try:
            picked = date(year, mm, dd)
        except ValueError:
            await message.answer(strings.MANUAL_CUSTOM_BAD)
            return
        # If the resulting date is already in the past, assume next year.
        if picked < today:
            try:
                picked = date(year + 1, mm, dd)
            except ValueError:
                await message.answer(strings.MANUAL_CUSTOM_BAD)
                return
        hour, minute = hh, mi
    elif m_time and current_date is not None:
        hour, minute = (int(g) for g in m_time.groups())
        picked = current_date
    else:
        await message.answer(strings.MANUAL_CUSTOM_BAD)
        return

    if not (0 <= hour < 24 and 0 <= minute < 60):
        await message.answer(strings.MANUAL_CUSTOM_BAD)
        return

    local = datetime(picked.year, picked.month, picked.day, hour, minute, tzinfo=tz)
    start_at_utc = local.astimezone(UTC)
    if start_at_utc <= now_utc():
        await message.answer(strings.MANUAL_CUSTOM_PAST)
        return

    await state.update_data(date=picked.isoformat(), start_at=start_at_utc.isoformat())
    await state.set_state(MasterAdd.EnteringComment)
    await message.answer(strings.MANUAL_ASK_COMMENT, reply_markup=skip_comment_kb())


def _render_confirm(
    *, client: Client, service: Service, start_at: datetime, comment: str | None, tz: ZoneInfo
) -> str:
    local = start_at.astimezone(tz)
    return strings.MANUAL_CONFIRM_CARD.format(
        client=client.name,
        phone=client.phone,
        service=service.name,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        notes=(comment or "—"),
    )


async def _load_client_service(
    session: AsyncSession, master: Master, data: dict[str, Any]
) -> tuple[Client | None, Service | None]:
    client = await session.get(Client, UUID(data["client_id"]))
    service = await ServiceRepository(session).get(UUID(data["service_id"]), master_id=master.id)
    return client, service


@router.message(MasterAdd.EnteringComment)
async def msg_comment(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    raw = (message.text or "").strip()[:_COMMENT_MAX]
    data = await state.get_data()
    client, service = await _load_client_service(session, master, data)
    if client is None or service is None:
        await state.clear()
        return
    await state.update_data(comment=raw or None)
    await state.set_state(MasterAdd.Confirming)
    tz = ZoneInfo(master.timezone)
    start_at = datetime.fromisoformat(data["start_at"])
    await message.answer(
        _render_confirm(client=client, service=service, start_at=start_at, comment=raw or None, tz=tz),
        reply_markup=confirm_add_kb(),
    )


@router.callback_query(SkipCommentCallback.filter(), MasterAdd.EnteringComment)
async def cb_skip_comment(
    callback: CallbackQuery,
    callback_data: SkipCommentCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    data = await state.get_data()
    client, service = await _load_client_service(session, master, data)
    if client is None or service is None:
        await state.clear()
        return
    await state.update_data(comment=None)
    await state.set_state(MasterAdd.Confirming)
    tz = ZoneInfo(master.timezone)
    start_at = datetime.fromisoformat(data["start_at"])
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            _render_confirm(client=client, service=service, start_at=start_at, comment=None, tz=tz),
            reply_markup=confirm_add_kb(),
        )


@router.callback_query(F.data == "master_add_save", MasterAdd.Confirming)
async def cb_confirm_save(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
    bot: Bot,
) -> None:
    data = await state.get_data()
    client, service = await _load_client_service(session, master, data)
    if client is None or service is None:
        await state.clear()
        await callback.answer(strings.MANUAL_CANCELED, show_alert=True)
        return

    start_at = datetime.fromisoformat(data["start_at"])
    comment: str | None = data.get("comment")
    svc = BookingService(session)
    try:
        appt = await svc.create_manual(
            master=master, client=client, service=service, start_at=start_at, comment=comment
        )
    except SlotAlreadyTaken:
        await session.refresh(master)
        await session.refresh(service)
        await callback.answer(strings.MANUAL_SLOT_TAKEN, show_alert=True)
        await state.set_state(MasterAdd.PickingSlot)
        tz = ZoneInfo(master.timezone)
        picked = start_at.astimezone(tz).date()
        slots = await svc.get_free_slots(master, service, picked, now=now_utc())
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(
                strings.MANUAL_ASK_SLOT, reply_markup=slots_grid_with_custom(slots, tz=tz)
            )
        return

    await callback.answer(strings.MANUAL_SAVED)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.MANUAL_SAVED)
    await state.clear()

    if client.tg_id is not None:
        tz = ZoneInfo(master.timezone)
        local = appt.start_at.astimezone(tz)
        text = strings.CLIENT_NOTIFY_MANUAL.format(
            date=local.strftime("%d.%m.%Y"),
            time=local.strftime("%H:%M"),
            service=service.name,
        )
        try:
            await bot.send_message(
                chat_id=client.tg_id, text=text, reply_markup=client_cancel_kb(appt.id)
            )
        except Exception:  # noqa: BLE001
            log.warning("client_notify_failed", client_tg=client.tg_id)
    log.info("manual_created", appointment_id=str(appt.id), master_tg=master.tg_id)


@router.callback_query(F.data == "master_add_cancel", MasterAdd.Confirming)
async def cb_confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer(strings.MANUAL_CANCELED)
    await state.clear()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.MANUAL_CANCELED)


@router.message(Command("cancel"), MasterAdd.PickingClient)
@router.message(Command("cancel"), MasterAdd.SearchingClient)
@router.message(Command("cancel"), MasterAdd.NewClientName)
@router.message(Command("cancel"), MasterAdd.NewClientPhone)
@router.message(Command("cancel"), MasterAdd.PickingService)
@router.message(Command("cancel"), MasterAdd.PickingDate)
@router.message(Command("cancel"), MasterAdd.PickingSlot)
@router.message(Command("cancel"), MasterAdd.EnteringCustomTime)
@router.message(Command("cancel"), MasterAdd.EnteringComment)
@router.message(Command("cancel"), MasterAdd.Confirming)
async def cmd_cancel_any(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(strings.MANUAL_CANCELED)
```

- [ ] **Step 2a: Cleanup imports**

After appending Part B, reorganize imports at the top of the file so all imports are in a single block (ruff will complain otherwise). No duplicate imports. Remove the inline `from sqlalchemy import select` from Part A and lift it to the top.

- [ ] **Step 3: Register router in `src/handlers/master/__init__.py`**

```python
from __future__ import annotations

from aiogram import Router

from src.handlers.master.add_manual import router as add_manual_router
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
router.include_router(add_manual_router)

__all__ = ["router"]
```

- [ ] **Step 4: Run Part B tests**

Run: `pytest tests/test_handlers_master_add_part_b.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Full suite still green**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 6: Quality gates + commit**

```bash
ruff check . && ruff format --check . && mypy src/ --strict && \
git add src/handlers/master/add_manual.py src/handlers/master/__init__.py tests/test_handlers_master_add_part_b.py && \
git commit -m "feat(master): Epic 5 /add handler part B — calendar, slots, comment, confirm"
```

---

## Task 10: Armenian translations

**Files:**
- Modify: `src/strings.py`

- [ ] **Step 1: Translate new Epic 5 keys in `_HY`**

Replace the Russian fallback values added in Task 6 inside the `_HY` dict with Armenian translations. Keys to translate (from Task 6 list): `MANUAL_PICK_CLIENT`, `MANUAL_NO_RECENT`, `MANUAL_SEARCH_PROMPT`, `MANUAL_SEARCH_EMPTY`, `MANUAL_ASK_NAME`, `MANUAL_NAME_BAD`, `MANUAL_ASK_PHONE`, `MANUAL_PHONE_BAD`, `MANUAL_PHONE_DUP`, `MANUAL_ASK_SERVICE`, `MANUAL_ASK_DATE`, `MANUAL_ASK_SLOT`, `MANUAL_CUSTOM_PROMPT`, `MANUAL_CUSTOM_BAD`, `MANUAL_CUSTOM_PAST`, `MANUAL_ASK_COMMENT`, `MANUAL_CONFIRM_CARD`, `MANUAL_SAVED`, `MANUAL_CANCELED`, `MANUAL_SLOT_TAKEN`, `MANUAL_BTN_SEARCH`, `MANUAL_BTN_NEW`, `MANUAL_BTN_SEARCH_CANCEL`, `MANUAL_BTN_DUP_USE`, `MANUAL_BTN_DUP_RETRY`, `MANUAL_BTN_CUSTOM_TIME`, `MANUAL_BTN_BACK`, `MANUAL_BTN_SKIP`, `MANUAL_BTN_SAVE`, `MANUAL_BTN_CANCEL`, `CLIENT_NOTIFY_MANUAL`, `CLIENT_CANCEL_BUTTON`, `CLIENT_CANCEL_DONE`, `CLIENT_CANCEL_UNAVAILABLE`, `MASTER_NOTIFY_CLIENT_CANCELED`.

**Handoff note:** the user has asked to handle the Armenian batch personally at the end. The implementer of this task will ping the user for the translations and then paste them into the file — do NOT guess Armenian.

- [ ] **Step 2: Verify placeholders preserved**

For keys with format placeholders (`{name}`, `{date}`, `{time}`, `{service}`, `{phone}`, `{client}`, `{notes}`), ensure the Armenian versions use the **same** placeholder names (untranslated).

- [ ] **Step 3: Full test run**

Run: `pytest -v`
Expected: all pass.

- [ ] **Step 4: Quality gates + commit**

```bash
ruff check src/strings.py && ruff format --check src/strings.py && mypy src/strings.py --strict && \
git add src/strings.py && \
git commit -m "i18n: Armenian translations for Epic 5 strings"
```

---

## Final gate: tag v0.5.0-epic-5

After Task 10 is green:

```bash
pytest -v                               # confirm all green
ruff check . && ruff format --check .   # confirm clean
mypy src/ --strict                      # confirm clean
git tag v0.5.0-epic-5
# DO NOT push — wait for explicit user authorization (project convention).
```

Update `memory/project_current_epic.md` to reflect Epic 5 closed + Epic 6 next.

---

## Quality targets

- Total tests after this epic: roughly 210–220 (180 after Task 6 + ~21 handler tests + 3 cancel + callbacks).
- Coverage:
  - `src/services/booking.py` `cancel_by_client` ≥95%.
  - `src/repositories/clients.py` new methods ≥95%.
  - `src/handlers/master/add_manual.py` ≥70%.
  - `src/handlers/client/cancel.py` ≥85%.
- ruff strict, mypy strict — clean.
- No new dependencies.
- No Alembic migration (schema unchanged).

## Notes for the implementer

- `MasterAdd` has 10 states, not 9 (spec wrote "9 состояний" colloquially — the concrete list in the spec's table has 10).
- `BookingService.create_manual` uses parameter `client: Client` and `comment: str | None = None`. Do NOT pass `client_id`, do NOT use `notes=`.
- Status in the DB is `'cancelled'` (British, two `l`s). Use this everywhere.
- `ApprovalCallback` field `action` is `Literal` — changing it to include `"cancel"` is the ONLY change to `src/callback_data/approval.py`.
- Never make up Armenian strings — Task 10 asks the user.
- Existing router naming convention: `router = Router(name="master_add_manual")`. Keep consistency with other routers.
- `ServiceRepository.list_active` — confirm by reading the file before calling.
- **Master DI convention:** `UserMiddleware` injects `master: Master | None` (see `src/middlewares/user.py`); existing handlers (`src/handlers/master/approve.py::route_approval`) use `master: Master | None` with an early `if master is None: return`. Follow this convention — the handler signatures in Tasks 8 and 9 show `master: Master` for brevity, but implement them as `master: Master | None` with a guard line at the top: `if master is None: return` (or `await callback.answer(...)` for callback handlers). Tests already pass a valid `Master` so this change doesn't break tests.
- Do not push branches or tags without explicit user authorization.
