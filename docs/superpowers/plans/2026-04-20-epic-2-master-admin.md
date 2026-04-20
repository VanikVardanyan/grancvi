# Epic 2 Implementation Plan — Master Registration and Admin Settings

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable a master (admin) to register via `/start`, manage their services (name + duration), and set weekly work hours. After this epic, a master's profile is complete enough to feed slot-availability computation in Epic 3.

**Architecture:** Layered — `handlers (aiogram Router) → services/repositories → db`. FSM state persists in Redis (RedisStorage). UX choices for this epic:
- **Phone** at registration: any non-empty string, required (cannot skip).
- **Work hours:** one interval per weekday for MVP (`{"mon": [["10:00","19:00"]]}`). Breaks are a separate flow, also one interval per day. Split-day is deferred (the JSONB shape allows it, but UI only writes one interval).
- Strings are hardcoded Russian in `src/strings.py` (Fluent i18n is a later epic).

**Tech Stack:** aiogram 3 (Router + RedisStorage + CallbackData), SQLAlchemy 2 async, asyncpg, pydantic-settings, structlog, pytest+pytest-asyncio.

---

## File Structure

Files this epic creates or modifies:

```
src/
  strings.py                          # NEW: hardcoded Russian copy
  fsm_storage.py                      # NEW: build RedisStorage from settings
  handlers/
    __init__.py                       # NEW: router composition
    master/
      __init__.py                     # NEW
      start.py                        # NEW: /start dispatcher + registration FSM
      menu.py                         # NEW: main menu reply keyboard + stubs for /today /add /calendar
      services.py                     # NEW: /services CRUD
      settings.py                     # NEW: /settings menu + work hours FSM
  repositories/
    __init__.py                       # NEW
    masters.py                        # NEW
    services.py                       # NEW
  fsm/
    __init__.py                       # NEW
    master_register.py                # NEW
    services.py                       # NEW
    work_hours.py                     # NEW
  callback_data/
    __init__.py                       # NEW
    services.py                       # NEW
    settings.py                       # NEW
  keyboards/
    __init__.py                       # NEW
    common.py                         # NEW: main menu ReplyKeyboard
    services.py                       # NEW
    settings.py                       # NEW
  utils/
    __init__.py                       # NEW
    work_hours.py                     # NEW: HH:MM parsing + shape validation
  main.py                             # MODIFY: RedisStorage, include master router
tests/
  test_repositories_masters.py        # NEW
  test_repositories_services.py       # NEW
  test_utils_work_hours.py            # NEW
  test_fsm_register_flow.py           # NEW (aiogram test via mocked event)
```

Each handler module exports a single `router: Router`. `src/handlers/__init__.py` composes them into one `master_router` to plug into `Dispatcher`.

---

## Task 1: RedisStorage, Router scaffold, strings module

Prep for the whole epic. Switch `Dispatcher` to `RedisStorage` (FSM storage — project rule), introduce router composition, and extract strings.

**Files:**
- Create: `src/fsm_storage.py`
- Create: `src/strings.py`
- Create: `src/handlers/__init__.py`, `src/handlers/master/__init__.py`
- Create: `src/handlers/master/start.py` (placeholder, just exposes `router`)
- Modify: `src/main.py`

- [ ] **Step 1: Create `src/strings.py`**

```python
from __future__ import annotations

# All user-facing strings for Epic 2. Ready to be replaced by Fluent later.

REGISTER_WELCOME = "Добро пожаловать! Давайте настроим ваш профиль мастера."
REGISTER_ASK_NAME = "Как к вам обращаться? (имя, как его увидят клиенты)"
REGISTER_ASK_PHONE = "Укажите телефон для связи."
REGISTER_DONE = "Готово! Профиль создан. Что дальше?"

START_UNKNOWN = "Нужна ссылка от клиники."
START_WELCOME_BACK = "С возвращением. Что дальше?"

MAIN_MENU_TODAY = "📅 Сегодня"
MAIN_MENU_ADD = "➕ Добавить запись"
MAIN_MENU_CALENDAR = "🗓 Календарь"
MAIN_MENU_SETTINGS = "⚙️ Настройки"

STUB_TODAY = "Здесь будет список записей на сегодня (Эпик 5)."
STUB_ADD = "Здесь будет ручное добавление записи (Эпик 5)."
STUB_CALENDAR = "Здесь будет календарь (Эпик 5)."

SETTINGS_MENU_TITLE = "Настройки"
SETTINGS_BTN_SERVICES = "Услуги"
SETTINGS_BTN_WORK_HOURS = "Часы работы"
SETTINGS_BTN_BREAKS = "Перерывы"

SERVICES_EMPTY = "Услуг пока нет. Добавьте первую."
SERVICES_LIST_TITLE = "Ваши услуги:"
SERVICES_BTN_ADD = "➕ Добавить услугу"
SERVICES_BTN_EDIT = "✏️"
SERVICES_BTN_DELETE = "🗑"
SERVICES_ADD_ASK_NAME = "Название услуги?"
SERVICES_ADD_ASK_DURATION = "Длительность в минутах? (целое число)"
SERVICES_ADD_BAD_DURATION = "Нужно целое число минут больше нуля."
SERVICES_ADDED = "Услуга добавлена."
SERVICES_DELETED = "Услуга удалена."
SERVICES_EDIT_MENU = "Что меняем?"
SERVICES_EDIT_BTN_NAME = "Название"
SERVICES_EDIT_BTN_DURATION = "Длительность"
SERVICES_EDIT_BTN_TOGGLE = "Вкл/выкл"
SERVICES_EDIT_NAME_PROMPT = "Новое название?"
SERVICES_EDIT_DURATION_PROMPT = "Новая длительность в минутах?"
SERVICES_UPDATED = "Услуга обновлена."

WORK_HOURS_TITLE = "Часы работы по дням недели:"
WORK_HOURS_DAY_OFF = "выходной"
WORK_HOURS_PICK_DAY = "Выберите день:"
WORK_HOURS_ASK_START = "Начало рабочего дня? Формат HH:MM, например 10:00."
WORK_HOURS_ASK_END = "Конец рабочего дня? Формат HH:MM, например 19:00."
WORK_HOURS_BAD_FORMAT = "Не разобрал. Ожидаю HH:MM, например 10:00."
WORK_HOURS_BAD_ORDER = "Конец должен быть позже начала."
WORK_HOURS_BTN_DAY_OFF = "Выходной"
WORK_HOURS_SAVED = "Сохранено."

WEEKDAYS: dict[str, str] = {
    "mon": "Пн",
    "tue": "Вт",
    "wed": "Ср",
    "thu": "Чт",
    "fri": "Пт",
    "sat": "Сб",
    "sun": "Вс",
}
```

- [ ] **Step 2: Create `src/fsm_storage.py`**

```python
from __future__ import annotations

from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from src.config import settings


def build_fsm_storage() -> RedisStorage:
    """Build aiogram RedisStorage from settings.redis_url."""
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    return RedisStorage(redis=redis)
```

- [ ] **Step 3: Create empty router packages**

`src/handlers/__init__.py`:

```python
from __future__ import annotations

from aiogram import Router

from src.handlers.master import router as master_router


def build_root_router() -> Router:
    root = Router(name="root")
    root.include_router(master_router)
    return root


__all__ = ["build_root_router"]
```

`src/handlers/master/__init__.py`:

```python
from __future__ import annotations

from aiogram import Router

from src.handlers.master.start import router as start_router

router = Router(name="master")
router.include_router(start_router)

__all__ = ["router"]
```

`src/handlers/master/start.py` (placeholder — keeps /start working; we rewrite it in Task 3):

```python
from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="master_start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer("hello")
```

- [ ] **Step 4: Rewrite `src/main.py` to use RedisStorage + root router**

Replace contents:

```python
from __future__ import annotations

import asyncio
import logging
from typing import Any

import structlog
from aiogram import Bot, Dispatcher
from aiogram.types import Message

from src.config import settings
from src.db.base import SessionMaker
from src.db.models import Client, Master
from src.fsm_storage import build_fsm_storage
from src.handlers import build_root_router
from src.middlewares.db import DbSessionMiddleware
from src.middlewares.user import UserMiddleware


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
    dp.include_router(build_root_router())
    return dp


async def main() -> None:
    configure_logging()
    bot = Bot(token=settings.bot_token)
    dp = build_dispatcher()
    log.info("bot_starting")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


# Re-exported so Message/Master/Client aren't unused imports — handler modules
# will import them from here too in later tasks.
_UNUSED: tuple[Any, ...] = (Message, Master, Client)


if __name__ == "__main__":
    asyncio.run(main())
```

Note: `Message`, `Master`, `Client` stay imported for type re-use in Task 3 — but to keep mypy/ruff happy RIGHT NOW without a noqa comment, remove them if linters complain. Simpler version (use this one if lint errors):

```python
from __future__ import annotations

import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher

from src.config import settings
from src.db.base import SessionMaker
from src.fsm_storage import build_fsm_storage
from src.handlers import build_root_router
from src.middlewares.db import DbSessionMiddleware
from src.middlewares.user import UserMiddleware


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
    dp.include_router(build_root_router())
    return dp


async def main() -> None:
    configure_logging()
    bot = Bot(token=settings.bot_token)
    dp = build_dispatcher()
    log.info("bot_starting")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
```

Use the simpler version.

- [ ] **Step 5: Run linters**

```bash
uv run ruff check .
uv run ruff format .
uv run mypy src/ tests/
```

Expected: clean.

- [ ] **Step 6: Run tests**

```bash
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/ -v
```

Expected: 7/7 still pass (no new tests yet, nothing broken).

- [ ] **Step 7: Rebuild and smoke-test in Telegram**

```bash
docker compose build app
docker compose up -d app
docker compose logs app --tail 30
```

Expected: `bot_starting` JSON line, no exceptions. Send `/start` in Telegram → still replies `hello` (placeholder handler).

- [ ] **Step 8: Commit**

```bash
git add src/strings.py src/fsm_storage.py src/handlers/ src/main.py
git commit -m "feat(bot): RedisStorage + root router scaffold, extract strings"
```

---

## Task 2: MasterRepository

Pure DB access for Master. This unlocks registration and main-menu dispatch.

**Files:**
- Create: `src/repositories/__init__.py`
- Create: `src/repositories/masters.py`
- Create: `tests/test_repositories_masters.py`

- [ ] **Step 1: Write failing test `tests/test_repositories_masters.py`**

```python
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.masters import MasterRepository


@pytest.mark.asyncio
async def test_get_by_tg_id_returns_none_when_absent(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    result = await repo.get_by_tg_id(404404)
    assert result is None


@pytest.mark.asyncio
async def test_create_and_read_roundtrip(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    created = await repo.create(tg_id=111, name="Анна", phone="+37411111111")
    await session.commit()

    fetched = await repo.get_by_tg_id(111)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Анна"
    assert fetched.phone == "+37411111111"
    assert fetched.timezone == "Asia/Yerevan"


@pytest.mark.asyncio
async def test_duplicate_tg_id_raises(session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    repo = MasterRepository(session)
    await repo.create(tg_id=222, name="Борис", phone="+37422222222")
    await session.commit()

    with pytest.raises(IntegrityError):
        await repo.create(tg_id=222, name="Борис-двойник", phone="+37400000000")
        await session.commit()
```

- [ ] **Step 2: Run tests, verify fail**

```bash
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_repositories_masters.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.repositories'` (or `...masters`).

- [ ] **Step 3: Implement `src/repositories/__init__.py`**

```python
from __future__ import annotations
```

- [ ] **Step 4: Implement `src/repositories/masters.py`**

```python
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master


class MasterRepository:
    """CRUD for Master."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_tg_id(self, tg_id: int) -> Master | None:
        return await self._session.scalar(select(Master).where(Master.tg_id == tg_id))

    async def create(
        self,
        *,
        tg_id: int,
        name: str,
        phone: str | None = None,
        timezone: str = "Asia/Yerevan",
    ) -> Master:
        master = Master(tg_id=tg_id, name=name, phone=phone, timezone=timezone)
        self._session.add(master)
        await self._session.flush()
        return master

    async def update_work_hours(self, master_id: Any, work_hours: dict[str, Any]) -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.work_hours = work_hours

    async def update_breaks(self, master_id: Any, breaks: dict[str, Any]) -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.breaks = breaks
```

- [ ] **Step 5: Run tests, verify pass**

```bash
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_repositories_masters.py -v
```

Expected: 3/3 pass.

- [ ] **Step 6: Linters**

```bash
uv run ruff check .
uv run ruff format .
uv run mypy src/ tests/
```

- [ ] **Step 7: Commit**

```bash
git add src/repositories/ tests/test_repositories_masters.py
git commit -m "feat(repo): MasterRepository with get_by_tg_id/create"
```

---

## Task 3: Master registration FSM + `/start` dispatcher + main menu keyboard

Now `/start` behaves conditionally:

1. If a `Master` already exists for this tg_id → show main menu reply keyboard.
2. Else if tg_id is in `ADMIN_TG_IDS` → start registration FSM (ask name → ask phone → save → show main menu).
3. Else if a `Client` exists (resolved by UserMiddleware as `data["client"]`) → greet (client flow arrives in Epic 4; for now, temporary polite message).
4. Else → `START_UNKNOWN`.

**Files:**
- Create: `src/fsm/__init__.py`, `src/fsm/master_register.py`
- Create: `src/keyboards/__init__.py`, `src/keyboards/common.py`
- Modify: `src/handlers/master/start.py`

- [ ] **Step 1: Create `src/fsm/__init__.py`**

```python
from __future__ import annotations
```

- [ ] **Step 2: Create `src/fsm/master_register.py`**

```python
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MasterRegister(StatesGroup):
    waiting_name = State()
    waiting_phone = State()
```

- [ ] **Step 3: Create `src/keyboards/__init__.py`**

```python
from __future__ import annotations
```

- [ ] **Step 4: Create `src/keyboards/common.py`**

```python
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from src import strings


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=strings.MAIN_MENU_TODAY),
                KeyboardButton(text=strings.MAIN_MENU_ADD),
            ],
            [
                KeyboardButton(text=strings.MAIN_MENU_CALENDAR),
                KeyboardButton(text=strings.MAIN_MENU_SETTINGS),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
```

- [ ] **Step 5: Rewrite `src/handlers/master/start.py`**

```python
from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src import strings
from src.config import settings
from src.db.models import Client, Master
from src.fsm.master_register import MasterRegister
from src.keyboards.common import main_menu
from src.repositories.masters import MasterRepository

router = Router(name="master_start")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


@router.message(CommandStart())
async def handle_start(
    message: Message,
    master: Master | None,
    client: Client | None,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    tg_id = message.from_user.id if message.from_user else None
    log.info(
        "start_received",
        tg_id=tg_id,
        has_master=master is not None,
        has_client=client is not None,
    )

    if master is not None:
        await state.clear()
        await message.answer(strings.START_WELCOME_BACK, reply_markup=main_menu())
        return

    if tg_id is not None and tg_id in settings.admin_tg_ids:
        await state.set_state(MasterRegister.waiting_name)
        await message.answer(strings.REGISTER_WELCOME)
        await message.answer(strings.REGISTER_ASK_NAME)
        return

    if client is not None:
        # Client flow lands in Epic 4. Temporary ack so testers know they were recognised.
        await message.answer("Привет! Запись через меню клиники появится позже.")
        return

    await message.answer(strings.START_UNKNOWN)


@router.message(MasterRegister.waiting_name)
async def register_handle_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(strings.REGISTER_ASK_NAME)
        return
    await state.update_data(name=name)
    await state.set_state(MasterRegister.waiting_phone)
    await message.answer(strings.REGISTER_ASK_PHONE)


@router.message(MasterRegister.waiting_phone)
async def register_handle_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    phone = (message.text or "").strip()
    if not phone:
        await message.answer(strings.REGISTER_ASK_PHONE)
        return
    if message.from_user is None:
        await state.clear()
        return

    data = await state.get_data()
    name: str = data["name"]

    repo = MasterRepository(session)
    await repo.create(tg_id=message.from_user.id, name=name, phone=phone)

    await state.clear()
    await message.answer(strings.REGISTER_DONE, reply_markup=main_menu())
```

Note on session commit: `DbSessionMiddleware` already commits at the end of the update if the handler returned without raising — no explicit commit needed here.

- [ ] **Step 6: Run linters**

```bash
uv run ruff check .
uv run ruff format .
uv run mypy src/ tests/
```

Expected: clean.

- [ ] **Step 7: Run tests**

```bash
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/ -v
```

Expected: 10/10 pass (3 new from Task 2 + existing 7).

- [ ] **Step 8: Smoke-test in Telegram**

```bash
docker compose build app && docker compose up -d app && docker compose logs app --tail 20
```

Then in Telegram:
1. `/start` — registration FSM starts (your tg_id is in ADMIN_TG_IDS, no Master row exists yet).
2. Send your name → bot asks phone.
3. Send any phone → bot answers `Готово!` and shows main menu (Сегодня / Добавить / Календарь / Настройки).
4. `/start` again → `С возвращением` + menu (already registered).

Verify row landed in DB:

```bash
docker compose exec postgres psql -U botik -d botik -c "SELECT tg_id, name, phone, timezone FROM masters;"
```

- [ ] **Step 9: Commit**

```bash
git add src/fsm/ src/keyboards/ src/handlers/master/start.py
git commit -m "feat(master): registration FSM + /start dispatcher + main menu"
```

---

## Task 4: Main-menu stub handlers + settings router skeleton

Register stubs for the reply-keyboard buttons so tapping them doesn't silently drop updates. `/settings` opens an inline menu with three entries (Услуги / Часы работы / Перерывы); the sub-handlers are filled in later tasks.

**Files:**
- Create: `src/handlers/master/menu.py`
- Create: `src/handlers/master/settings.py`
- Create: `src/callback_data/__init__.py`, `src/callback_data/settings.py`
- Create: `src/keyboards/settings.py`
- Modify: `src/handlers/master/__init__.py`

- [ ] **Step 1: Create `src/callback_data/__init__.py`**

```python
from __future__ import annotations
```

- [ ] **Step 2: Create `src/callback_data/settings.py`**

```python
from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class SettingsCallback(CallbackData, prefix="set"):
    section: Literal["services", "hours", "breaks"]
```

- [ ] **Step 3: Create `src/keyboards/settings.py`**

```python
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src import strings
from src.callback_data.settings import SettingsCallback


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_SERVICES,
                    callback_data=SettingsCallback(section="services").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_WORK_HOURS,
                    callback_data=SettingsCallback(section="hours").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_BREAKS,
                    callback_data=SettingsCallback(section="breaks").pack(),
                )
            ],
        ]
    )
```

- [ ] **Step 4: Create `src/handlers/master/menu.py`**

```python
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from src import strings
from src.db.models import Master
from src.keyboards.settings import settings_menu

router = Router(name="master_menu")


# Guard everything in this router by master presence — these buttons exist only
# for registered masters. If no master in data, let other routers handle it.
@router.message(F.text == strings.MAIN_MENU_TODAY)
async def handle_today(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await message.answer(strings.STUB_TODAY)


@router.message(F.text == strings.MAIN_MENU_ADD)
async def handle_add(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await message.answer(strings.STUB_ADD)


@router.message(F.text == strings.MAIN_MENU_CALENDAR)
async def handle_calendar(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await message.answer(strings.STUB_CALENDAR)


@router.message(F.text == strings.MAIN_MENU_SETTINGS)
async def handle_settings(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await message.answer(strings.SETTINGS_MENU_TITLE, reply_markup=settings_menu())
```

- [ ] **Step 5: Create `src/handlers/master/settings.py` (placeholder)**

```python
from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery

from src.callback_data.settings import SettingsCallback

router = Router(name="master_settings")


@router.callback_query(SettingsCallback.filter())
async def handle_settings_section(
    callback: CallbackQuery, callback_data: SettingsCallback
) -> None:
    # Filled in by Tasks 6 (services), 9 (hours). For now acknowledge and stub.
    await callback.answer(f"Раздел «{callback_data.section}» — скоро.")
```

- [ ] **Step 6: Update `src/handlers/master/__init__.py`**

```python
from __future__ import annotations

from aiogram import Router

from src.handlers.master.menu import router as menu_router
from src.handlers.master.settings import router as settings_router
from src.handlers.master.start import router as start_router

router = Router(name="master")
router.include_router(start_router)
router.include_router(menu_router)
router.include_router(settings_router)

__all__ = ["router"]
```

- [ ] **Step 7: Linters + tests**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/ -v
```

Expected: clean; 10/10 pass (nothing new to test, stubs only).

- [ ] **Step 8: Smoke-test in Telegram**

```bash
docker compose build app && docker compose up -d app
```

In Telegram:
- Tap `📅 Сегодня` → stub message.
- Tap `⚙️ Настройки` → inline menu with three buttons appears.
- Tap any section → toast `Раздел «X» — скоро.`

- [ ] **Step 9: Commit**

```bash
git add src/callback_data/ src/keyboards/settings.py src/handlers/master/menu.py src/handlers/master/settings.py src/handlers/master/__init__.py
git commit -m "feat(master): main-menu stubs + settings inline menu skeleton"
```

---

## Task 5: ServiceRepository

**Files:**
- Create: `src/repositories/services.py`
- Create: `tests/test_repositories_services.py`

- [ ] **Step 1: Write failing test `tests/test_repositories_services.py`**

```python
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.repositories.services import ServiceRepository


async def _make_master(session: AsyncSession, tg_id: int = 555) -> Master:
    master = Master(tg_id=tg_id, name="Мастер")
    session.add(master)
    await session.flush()
    return master


@pytest.mark.asyncio
async def test_list_active_empty(session: AsyncSession) -> None:
    master = await _make_master(session)
    repo = ServiceRepository(session)
    result = await repo.list_active(master.id)
    assert result == []


@pytest.mark.asyncio
async def test_create_and_list(session: AsyncSession) -> None:
    master = await _make_master(session)
    repo = ServiceRepository(session)

    a = await repo.create(master_id=master.id, name="Чистка", duration_min=45)
    b = await repo.create(master_id=master.id, name="Пломба", duration_min=30)
    await session.commit()

    result = await repo.list_active(master.id)
    assert {s.id for s in result} == {a.id, b.id}
    assert all(s.active for s in result)


@pytest.mark.asyncio
async def test_update_name_and_duration(session: AsyncSession) -> None:
    master = await _make_master(session)
    repo = ServiceRepository(session)
    s = await repo.create(master_id=master.id, name="Old", duration_min=20)
    await session.commit()

    await repo.update(s.id, master_id=master.id, name="New", duration_min=35)
    await session.commit()

    refreshed = await repo.get(s.id, master_id=master.id)
    assert refreshed is not None
    assert refreshed.name == "New"
    assert refreshed.duration_min == 35


@pytest.mark.asyncio
async def test_toggle_active_hides_from_list(session: AsyncSession) -> None:
    master = await _make_master(session)
    repo = ServiceRepository(session)
    s = await repo.create(master_id=master.id, name="Тест", duration_min=20)
    await session.commit()

    await repo.set_active(s.id, master_id=master.id, active=False)
    await session.commit()

    assert await repo.list_active(master.id) == []
    # but get() by id still finds it — deletion is soft
    assert await repo.get(s.id, master_id=master.id) is not None


@pytest.mark.asyncio
async def test_update_other_masters_service_is_noop(session: AsyncSession) -> None:
    alice = await _make_master(session, tg_id=1)
    bob = await _make_master(session, tg_id=2)
    repo = ServiceRepository(session)

    s = await repo.create(master_id=alice.id, name="Alice's", duration_min=20)
    await session.commit()

    result = await repo.update(s.id, master_id=bob.id, name="Hijacked", duration_min=99)
    assert result is None
    refreshed = await repo.get(s.id, master_id=alice.id)
    assert refreshed is not None
    assert refreshed.name == "Alice's"
```

- [ ] **Step 2: Run tests, verify fail**

```bash
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_repositories_services.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.repositories.services'`.

- [ ] **Step 3: Implement `src/repositories/services.py`**

```python
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Service


class ServiceRepository:
    """CRUD for Service (a master's offered treatments)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self, master_id: UUID) -> list[Service]:
        stmt = (
            select(Service)
            .where(Service.master_id == master_id, Service.active.is_(True))
            .order_by(Service.position, Service.created_at)
        )
        return list((await self._session.scalars(stmt)).all())

    async def get(self, service_id: UUID, *, master_id: UUID) -> Service | None:
        stmt = select(Service).where(
            Service.id == service_id, Service.master_id == master_id
        )
        return await self._session.scalar(stmt)

    async def create(
        self, *, master_id: UUID, name: str, duration_min: int
    ) -> Service:
        service = Service(master_id=master_id, name=name, duration_min=duration_min)
        self._session.add(service)
        await self._session.flush()
        return service

    async def update(
        self,
        service_id: UUID,
        *,
        master_id: UUID,
        name: str | None = None,
        duration_min: int | None = None,
    ) -> Service | None:
        service = await self.get(service_id, master_id=master_id)
        if service is None:
            return None
        if name is not None:
            service.name = name
        if duration_min is not None:
            service.duration_min = duration_min
        return service

    async def set_active(
        self, service_id: UUID, *, master_id: UUID, active: bool
    ) -> Service | None:
        service = await self.get(service_id, master_id=master_id)
        if service is None:
            return None
        service.active = active
        return service
```

- [ ] **Step 4: Run tests, verify pass**

```bash
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/test_repositories_services.py -v
```

Expected: 5/5 pass.

- [ ] **Step 5: Linters**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/
```

- [ ] **Step 6: Commit**

```bash
git add src/repositories/services.py tests/test_repositories_services.py
git commit -m "feat(repo): ServiceRepository with soft-delete list/get/update/toggle"
```

---

## Task 6: Services list view + add FSM

Wire the `services` branch of the settings inline menu and `/services` command. Implement list view and add-service FSM (name → duration → save).

**Files:**
- Create: `src/fsm/services.py`
- Create: `src/callback_data/services.py`
- Create: `src/keyboards/services.py`
- Create: `src/handlers/master/services.py`
- Modify: `src/handlers/master/__init__.py`
- Modify: `src/handlers/master/settings.py` (dispatch `services` section to the services router helper)

- [ ] **Step 1: Create `src/fsm/services.py`**

```python
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ServiceAdd(StatesGroup):
    waiting_name = State()
    waiting_duration = State()


class ServiceEditName(StatesGroup):
    waiting_name = State()


class ServiceEditDuration(StatesGroup):
    waiting_duration = State()
```

- [ ] **Step 2: Create `src/callback_data/services.py`**

```python
from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class ServiceAction(CallbackData, prefix="svc"):
    action: Literal["add", "edit", "delete", "edit_name", "edit_duration", "toggle", "back"]
    service_id: UUID | None = None
```

- [ ] **Step 3: Create `src/keyboards/services.py`**

```python
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src import strings
from src.callback_data.services import ServiceAction
from src.db.models import Service


def services_list(services: list[Service]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for svc in services:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{svc.name} · {svc.duration_min} мин",
                    callback_data=ServiceAction(action="edit", service_id=svc.id).pack(),
                ),
                InlineKeyboardButton(
                    text=strings.SERVICES_BTN_DELETE,
                    callback_data=ServiceAction(action="delete", service_id=svc.id).pack(),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.SERVICES_BTN_ADD,
                callback_data=ServiceAction(action="add").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_menu(service_id: UUID) -> InlineKeyboardMarkup:
    from uuid import UUID as _UUID  # silence mypy "unused" if linter flags it

    assert isinstance(service_id, _UUID)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.SERVICES_EDIT_BTN_NAME,
                    callback_data=ServiceAction(
                        action="edit_name", service_id=service_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SERVICES_EDIT_BTN_DURATION,
                    callback_data=ServiceAction(
                        action="edit_duration", service_id=service_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SERVICES_EDIT_BTN_TOGGLE,
                    callback_data=ServiceAction(
                        action="toggle", service_id=service_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="← назад",
                    callback_data=ServiceAction(action="back").pack(),
                )
            ],
        ]
    )
```

Replace the kludgy `from uuid import UUID as _UUID` block with a clean `from uuid import UUID` at the top of the file if ruff is happy:

Cleaner version of `src/keyboards/services.py`:

```python
from __future__ import annotations

from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src import strings
from src.callback_data.services import ServiceAction
from src.db.models import Service


def services_list(services: list[Service]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for svc in services:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{svc.name} · {svc.duration_min} мин",
                    callback_data=ServiceAction(action="edit", service_id=svc.id).pack(),
                ),
                InlineKeyboardButton(
                    text=strings.SERVICES_BTN_DELETE,
                    callback_data=ServiceAction(action="delete", service_id=svc.id).pack(),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.SERVICES_BTN_ADD,
                callback_data=ServiceAction(action="add").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_menu(service_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.SERVICES_EDIT_BTN_NAME,
                    callback_data=ServiceAction(
                        action="edit_name", service_id=service_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SERVICES_EDIT_BTN_DURATION,
                    callback_data=ServiceAction(
                        action="edit_duration", service_id=service_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SERVICES_EDIT_BTN_TOGGLE,
                    callback_data=ServiceAction(
                        action="toggle", service_id=service_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="← назад",
                    callback_data=ServiceAction(action="back").pack(),
                )
            ],
        ]
    )
```

Use the cleaner version.

- [ ] **Step 4: Create `src/handlers/master/services.py`**

```python
from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src import strings
from src.callback_data.services import ServiceAction
from src.db.models import Master
from src.fsm.services import ServiceAdd, ServiceEditDuration, ServiceEditName
from src.keyboards.services import edit_menu, services_list
from src.repositories.services import ServiceRepository

router = Router(name="master_services")


async def _render_list(
    target: Message,
    master: Master,
    session: AsyncSession,
) -> None:
    repo = ServiceRepository(session)
    svcs = await repo.list_active(master.id)
    if not svcs:
        await target.answer(strings.SERVICES_EMPTY, reply_markup=services_list([]))
        return
    await target.answer(strings.SERVICES_LIST_TITLE, reply_markup=services_list(svcs))


@router.message(Command("services"))
async def cmd_services(
    message: Message, master: Master | None, session: AsyncSession
) -> None:
    if master is None:
        return
    await _render_list(message, master, session)


@router.callback_query(ServiceAction.filter(F.action == "add"))
async def cb_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ServiceAdd.waiting_name)
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.SERVICES_ADD_ASK_NAME)


@router.message(ServiceAdd.waiting_name)
async def add_handle_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(strings.SERVICES_ADD_ASK_NAME)
        return
    await state.update_data(name=name)
    await state.set_state(ServiceAdd.waiting_duration)
    await message.answer(strings.SERVICES_ADD_ASK_DURATION)


@router.message(ServiceAdd.waiting_duration)
async def add_handle_duration(
    message: Message,
    state: FSMContext,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await state.clear()
        return
    raw = (message.text or "").strip()
    try:
        duration = int(raw)
    except ValueError:
        await message.answer(strings.SERVICES_ADD_BAD_DURATION)
        return
    if duration <= 0:
        await message.answer(strings.SERVICES_ADD_BAD_DURATION)
        return

    data = await state.get_data()
    name: str = data["name"]
    repo = ServiceRepository(session)
    await repo.create(master_id=master.id, name=name, duration_min=duration)

    await state.clear()
    await message.answer(strings.SERVICES_ADDED)
    await _render_list(message, master, session)
```

- [ ] **Step 5: Update `src/handlers/master/settings.py`**

Replace the placeholder `handle_settings_section` with a dispatcher that opens the services list when `section == "services"`:

```python
from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src import strings
from src.callback_data.settings import SettingsCallback
from src.db.models import Master
from src.keyboards.services import services_list
from src.repositories.services import ServiceRepository

router = Router(name="master_settings")


@router.callback_query(SettingsCallback.filter())
async def handle_settings_section(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await callback.answer()
        return

    if callback_data.section == "services":
        repo = ServiceRepository(session)
        svcs = await repo.list_active(master.id)
        await callback.answer()
        if callback.message is not None and hasattr(callback.message, "answer"):
            title = strings.SERVICES_LIST_TITLE if svcs else strings.SERVICES_EMPTY
            await callback.message.answer(title, reply_markup=services_list(svcs))
        return

    # hours / breaks are wired in Tasks 9–10.
    await callback.answer(f"Раздел «{callback_data.section}» — скоро.")
```

- [ ] **Step 6: Update `src/handlers/master/__init__.py`**

```python
from __future__ import annotations

from aiogram import Router

from src.handlers.master.menu import router as menu_router
from src.handlers.master.services import router as services_router
from src.handlers.master.settings import router as settings_router
from src.handlers.master.start import router as start_router

router = Router(name="master")
router.include_router(start_router)
router.include_router(menu_router)
router.include_router(services_router)
router.include_router(settings_router)

__all__ = ["router"]
```

- [ ] **Step 7: Linters + tests**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/ -v
```

Expected: 15/15 pass (5 new from Task 5 + existing 10).

- [ ] **Step 8: Smoke-test**

```bash
docker compose build app && docker compose up -d app
```

In Telegram: `/services` → "Услуг пока нет." + add button → tap Add → name → duration → list refreshes.

Also: `/settings` → tap `Услуги` → same list.

- [ ] **Step 9: Commit**

```bash
git add src/fsm/services.py src/callback_data/services.py src/keyboards/services.py src/handlers/master/services.py src/handlers/master/settings.py src/handlers/master/__init__.py
git commit -m "feat(services): list + add FSM via /services and settings menu"
```

---

## Task 7: Services edit, delete, active-toggle

**Files:**
- Modify: `src/handlers/master/services.py`

Add handlers for `edit`, `delete`, `toggle`, `edit_name`, `edit_duration`, `back`.

- [ ] **Step 1: Extend `src/handlers/master/services.py`**

Append to the existing file:

```python
@router.callback_query(ServiceAction.filter(F.action == "edit"))
async def cb_edit(
    callback: CallbackQuery, callback_data: ServiceAction
) -> None:
    if callback_data.service_id is None:
        await callback.answer()
        return
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.SERVICES_EDIT_MENU, reply_markup=edit_menu(callback_data.service_id)
        )


@router.callback_query(ServiceAction.filter(F.action == "delete"))
async def cb_delete(
    callback: CallbackQuery,
    callback_data: ServiceAction,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None or callback_data.service_id is None:
        await callback.answer()
        return
    repo = ServiceRepository(session)
    await repo.set_active(callback_data.service_id, master_id=master.id, active=False)
    await callback.answer(strings.SERVICES_DELETED)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await _render_list(callback.message, master, session)


@router.callback_query(ServiceAction.filter(F.action == "toggle"))
async def cb_toggle(
    callback: CallbackQuery,
    callback_data: ServiceAction,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None or callback_data.service_id is None:
        await callback.answer()
        return
    repo = ServiceRepository(session)
    svc = await repo.get(callback_data.service_id, master_id=master.id)
    if svc is None:
        await callback.answer()
        return
    await repo.set_active(svc.id, master_id=master.id, active=not svc.active)
    await callback.answer(strings.SERVICES_UPDATED)


@router.callback_query(ServiceAction.filter(F.action == "edit_name"))
async def cb_edit_name(
    callback: CallbackQuery,
    callback_data: ServiceAction,
    state: FSMContext,
) -> None:
    if callback_data.service_id is None:
        await callback.answer()
        return
    await state.set_state(ServiceEditName.waiting_name)
    await state.update_data(service_id=str(callback_data.service_id))
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.SERVICES_EDIT_NAME_PROMPT)


@router.message(ServiceEditName.waiting_name)
async def handle_edit_name(
    message: Message,
    state: FSMContext,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await state.clear()
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer(strings.SERVICES_EDIT_NAME_PROMPT)
        return
    data = await state.get_data()
    service_id = UUID(data["service_id"])
    repo = ServiceRepository(session)
    await repo.update(service_id, master_id=master.id, name=name)
    await state.clear()
    await message.answer(strings.SERVICES_UPDATED)
    await _render_list(message, master, session)


@router.callback_query(ServiceAction.filter(F.action == "edit_duration"))
async def cb_edit_duration(
    callback: CallbackQuery,
    callback_data: ServiceAction,
    state: FSMContext,
) -> None:
    if callback_data.service_id is None:
        await callback.answer()
        return
    await state.set_state(ServiceEditDuration.waiting_duration)
    await state.update_data(service_id=str(callback_data.service_id))
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.SERVICES_EDIT_DURATION_PROMPT)


@router.message(ServiceEditDuration.waiting_duration)
async def handle_edit_duration(
    message: Message,
    state: FSMContext,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await state.clear()
        return
    try:
        duration = int((message.text or "").strip())
    except ValueError:
        await message.answer(strings.SERVICES_ADD_BAD_DURATION)
        return
    if duration <= 0:
        await message.answer(strings.SERVICES_ADD_BAD_DURATION)
        return
    data = await state.get_data()
    service_id = UUID(data["service_id"])
    repo = ServiceRepository(session)
    await repo.update(service_id, master_id=master.id, duration_min=duration)
    await state.clear()
    await message.answer(strings.SERVICES_UPDATED)
    await _render_list(message, master, session)


@router.callback_query(ServiceAction.filter(F.action == "back"))
async def cb_back(
    callback: CallbackQuery, master: Master | None, session: AsyncSession
) -> None:
    if master is None:
        await callback.answer()
        return
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await _render_list(callback.message, master, session)
```

Note: `from uuid import UUID` is already at the top of the file from Task 6 — the `UUID(data["service_id"])` calls above use it directly.

- [ ] **Step 2: Linters + tests**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/ -v
```

Expected: 15/15 pass.

- [ ] **Step 3: Smoke-test**

In Telegram:
- `/services` → tap a service → edit menu appears.
- Tap `Название` → send new name → list refreshes with updated name.
- Tap `Длительность` → send new duration → list refreshes.
- Tap `Вкл/выкл` → service disappears from active list.
- Tap `🗑` on another service → it's soft-deleted.

- [ ] **Step 4: Commit**

```bash
git add src/handlers/master/services.py
git commit -m "feat(services): edit name/duration, toggle active, soft-delete"
```

---

## Task 8: Work-hours parsing utility

Pure function: parse HH:MM, validate ordering, shape-check the JSONB structure. Fully covered by unit tests (no DB).

**Files:**
- Create: `src/utils/__init__.py`
- Create: `src/utils/work_hours.py`
- Create: `tests/test_utils_work_hours.py`

- [ ] **Step 1: Write failing test `tests/test_utils_work_hours.py`**

```python
from __future__ import annotations

import pytest

from src.utils.work_hours import (
    InvalidTimeFormat,
    InvalidTimeOrder,
    parse_hhmm,
    set_day_hours,
    set_day_off,
)


def test_parse_hhmm_valid() -> None:
    assert parse_hhmm("10:00") == (10, 0)
    assert parse_hhmm("09:30") == (9, 30)
    assert parse_hhmm("23:59") == (23, 59)
    assert parse_hhmm("00:00") == (0, 0)


def test_parse_hhmm_with_whitespace() -> None:
    assert parse_hhmm("  10:00  ") == (10, 0)


@pytest.mark.parametrize(
    "bad",
    ["", "10", "10:", ":00", "25:00", "10:60", "abc", "10:5", "1:00", "10.00"],
)
def test_parse_hhmm_invalid(bad: str) -> None:
    with pytest.raises(InvalidTimeFormat):
        parse_hhmm(bad)


def test_set_day_hours_empty_state() -> None:
    result = set_day_hours({}, "mon", "10:00", "19:00")
    assert result == {"mon": [["10:00", "19:00"]]}


def test_set_day_hours_overwrites_existing() -> None:
    current: dict[str, list[list[str]]] = {"mon": [["09:00", "18:00"]]}
    result = set_day_hours(current, "mon", "10:00", "19:00")
    assert result == {"mon": [["10:00", "19:00"]]}


def test_set_day_hours_rejects_end_before_start() -> None:
    with pytest.raises(InvalidTimeOrder):
        set_day_hours({}, "mon", "19:00", "10:00")


def test_set_day_hours_rejects_end_equal_to_start() -> None:
    with pytest.raises(InvalidTimeOrder):
        set_day_hours({}, "mon", "10:00", "10:00")


def test_set_day_off_removes_entry() -> None:
    current: dict[str, list[list[str]]] = {"mon": [["10:00", "19:00"]], "tue": [["11:00", "20:00"]]}
    result = set_day_off(current, "mon")
    assert result == {"tue": [["11:00", "20:00"]]}


def test_set_day_off_noop_when_absent() -> None:
    assert set_day_off({}, "sun") == {}


def test_immutable_does_not_mutate_input() -> None:
    original: dict[str, list[list[str]]] = {"mon": [["09:00", "18:00"]]}
    set_day_hours(original, "tue", "10:00", "19:00")
    assert original == {"mon": [["09:00", "18:00"]]}  # unchanged
```

- [ ] **Step 2: Run tests, verify fail**

```bash
uv run pytest tests/test_utils_work_hours.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.utils.work_hours'`.

- [ ] **Step 3: Create `src/utils/__init__.py`**

```python
from __future__ import annotations
```

- [ ] **Step 4: Implement `src/utils/work_hours.py`**

```python
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

VALID_DAYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})
_HHMM_RE = re.compile(r"^(?P<h>\d{2}):(?P<m>\d{2})$")


class InvalidTimeFormat(ValueError):
    """Raised when a string isn't HH:MM (two digits, colon, two digits, 0-23/0-59)."""


class InvalidTimeOrder(ValueError):
    """Raised when end time is not strictly after start time."""


def parse_hhmm(raw: str) -> tuple[int, int]:
    stripped = raw.strip()
    match = _HHMM_RE.match(stripped)
    if not match:
        raise InvalidTimeFormat(stripped)
    hour = int(match.group("h"))
    minute = int(match.group("m"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise InvalidTimeFormat(stripped)
    return (hour, minute)


def _as_minutes(hhmm: tuple[int, int]) -> int:
    return hhmm[0] * 60 + hhmm[1]


def _normalise(hhmm: tuple[int, int]) -> str:
    return f"{hhmm[0]:02d}:{hhmm[1]:02d}"


def set_day_hours(
    current: dict[str, Any],
    day: str,
    start_raw: str,
    end_raw: str,
) -> dict[str, Any]:
    """Return a new dict with `day` set to a single interval [start, end].

    Raises InvalidTimeFormat / InvalidTimeOrder. Does not mutate `current`.
    """
    if day not in VALID_DAYS:
        raise ValueError(f"unknown day: {day!r}")
    start = parse_hhmm(start_raw)
    end = parse_hhmm(end_raw)
    if _as_minutes(end) <= _as_minutes(start):
        raise InvalidTimeOrder(f"{start_raw} >= {end_raw}")
    out: dict[str, Any] = deepcopy(current)
    out[day] = [[_normalise(start), _normalise(end)]]
    return out


def set_day_off(current: dict[str, Any], day: str) -> dict[str, Any]:
    """Return a new dict with `day` removed (== day off)."""
    if day not in VALID_DAYS:
        raise ValueError(f"unknown day: {day!r}")
    out: dict[str, Any] = deepcopy(current)
    out.pop(day, None)
    return out
```

- [ ] **Step 5: Run tests, verify pass**

```bash
uv run pytest tests/test_utils_work_hours.py -v
```

Expected: all pass.

- [ ] **Step 6: Linters**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/
```

- [ ] **Step 7: Commit**

```bash
git add src/utils/ tests/test_utils_work_hours.py
git commit -m "feat(utils): work_hours HH:MM parsing + immutable day setters"
```

---

## Task 9: Work-hours FSM + settings submenu

Wire the `hours` section of the settings inline menu. UX:

1. User opens `⚙️ Настройки → Часы работы`.
2. Bot shows inline keyboard: one row per weekday with current hours or "выходной", plus a "Готово" button.
3. Tap on a day → bot sends message "Начало рабочего дня? HH:MM" with "Выходной" button below.
4. User types `10:00` → "Конец?" → `19:00` → saved, re-renders the day list with updated row.
5. Or user taps "Выходной" → clears the day and re-renders.

**Files:**
- Create: `src/fsm/work_hours.py`
- Modify: `src/callback_data/settings.py` (add `WorkHoursDay` callback)
- Modify: `src/keyboards/settings.py` (add `work_hours_list`)
- Modify: `src/handlers/master/settings.py`

- [ ] **Step 1: Create `src/fsm/work_hours.py`**

```python
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class WorkHoursEdit(StatesGroup):
    waiting_start = State()
    waiting_end = State()
```

- [ ] **Step 2: Extend `src/callback_data/settings.py`**

Append:

```python
from typing import Literal as _Literal


class WorkHoursDay(CallbackData, prefix="wh"):
    action: _Literal["pick", "day_off", "done"]
    day: str = ""  # "mon".."sun" for action="pick"|"day_off", empty for "done"
```

Final file content:

```python
from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class SettingsCallback(CallbackData, prefix="set"):
    section: Literal["services", "hours", "breaks"]


class WorkHoursDay(CallbackData, prefix="wh"):
    action: Literal["pick", "day_off", "done"]
    day: str = ""
```

- [ ] **Step 3: Extend `src/keyboards/settings.py`**

Add `work_hours_list` and `work_hours_day_prompt` helpers:

```python
from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src import strings
from src.callback_data.settings import SettingsCallback, WorkHoursDay


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_SERVICES,
                    callback_data=SettingsCallback(section="services").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_WORK_HOURS,
                    callback_data=SettingsCallback(section="hours").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_BREAKS,
                    callback_data=SettingsCallback(section="breaks").pack(),
                )
            ],
        ]
    )


def _format_day_label(day_code: str, work_hours: dict[str, Any]) -> str:
    label = strings.WEEKDAYS[day_code]
    intervals = work_hours.get(day_code)
    if not intervals:
        return f"{label}: {strings.WORK_HOURS_DAY_OFF}"
    first = intervals[0]
    return f"{label}: {first[0]}–{first[1]}"


def work_hours_list(work_hours: dict[str, Any]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for code in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_format_day_label(code, work_hours),
                    callback_data=WorkHoursDay(action="pick", day=code).pack(),
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="Готово", callback_data=WorkHoursDay(action="done").pack())]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def work_hours_day_prompt(day: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.WORK_HOURS_BTN_DAY_OFF,
                    callback_data=WorkHoursDay(action="day_off", day=day).pack(),
                )
            ]
        ]
    )
```

- [ ] **Step 4: Rewrite `src/handlers/master/settings.py`**

```python
from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src import strings
from src.callback_data.settings import SettingsCallback, WorkHoursDay
from src.db.models import Master
from src.fsm.work_hours import WorkHoursEdit
from src.keyboards.services import services_list
from src.keyboards.settings import work_hours_day_prompt, work_hours_list
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.utils.work_hours import (
    InvalidTimeFormat,
    InvalidTimeOrder,
    set_day_hours,
    set_day_off,
)

router = Router(name="master_settings")


async def _render_work_hours(
    target: Message, master: Master
) -> None:
    await target.answer(
        strings.WORK_HOURS_TITLE, reply_markup=work_hours_list(master.work_hours)
    )


@router.callback_query(SettingsCallback.filter())
async def handle_settings_section(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await callback.answer()
        return

    if callback_data.section == "services":
        repo = ServiceRepository(session)
        svcs = await repo.list_active(master.id)
        await callback.answer()
        if callback.message is not None and hasattr(callback.message, "answer"):
            title = strings.SERVICES_LIST_TITLE if svcs else strings.SERVICES_EMPTY
            await callback.message.answer(title, reply_markup=services_list(svcs))
        return

    if callback_data.section == "hours":
        await callback.answer()
        if callback.message is not None and hasattr(callback.message, "answer"):
            await _render_work_hours(callback.message, master)
        return

    # breaks wired later (out of scope for this epic beyond stub)
    await callback.answer(f"Раздел «{callback_data.section}» — скоро.")


@router.callback_query(WorkHoursDay.filter(F.action == "pick"))
async def cb_pick_day(
    callback: CallbackQuery,
    callback_data: WorkHoursDay,
    state: FSMContext,
) -> None:
    await state.set_state(WorkHoursEdit.waiting_start)
    await state.update_data(day=callback_data.day)
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.WORK_HOURS_ASK_START,
            reply_markup=work_hours_day_prompt(callback_data.day),
        )


@router.callback_query(WorkHoursDay.filter(F.action == "day_off"))
async def cb_day_off(
    callback: CallbackQuery,
    callback_data: WorkHoursDay,
    state: FSMContext,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await callback.answer()
        return
    await state.clear()
    updated = set_day_off(master.work_hours, callback_data.day)
    repo = MasterRepository(session)
    await repo.update_work_hours(master.id, updated)
    master.work_hours = updated
    await callback.answer(strings.WORK_HOURS_SAVED)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await _render_work_hours(callback.message, master)


@router.callback_query(WorkHoursDay.filter(F.action == "done"))
async def cb_work_hours_done(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Сохранено.")


@router.message(WorkHoursEdit.waiting_start)
async def wh_handle_start(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        from src.utils.work_hours import parse_hhmm

        parse_hhmm(raw)
    except InvalidTimeFormat:
        await message.answer(strings.WORK_HOURS_BAD_FORMAT)
        return
    await state.update_data(start=raw)
    await state.set_state(WorkHoursEdit.waiting_end)
    await message.answer(strings.WORK_HOURS_ASK_END)


@router.message(WorkHoursEdit.waiting_end)
async def wh_handle_end(
    message: Message,
    state: FSMContext,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await state.clear()
        return
    raw_end = (message.text or "").strip()
    data = await state.get_data()
    day: str = data["day"]
    raw_start: str = data["start"]
    try:
        updated = set_day_hours(master.work_hours, day, raw_start, raw_end)
    except InvalidTimeFormat:
        await message.answer(strings.WORK_HOURS_BAD_FORMAT)
        return
    except InvalidTimeOrder:
        await message.answer(strings.WORK_HOURS_BAD_ORDER)
        return

    repo = MasterRepository(session)
    await repo.update_work_hours(master.id, updated)
    master.work_hours = updated
    await state.clear()
    await message.answer(strings.WORK_HOURS_SAVED)
    await _render_work_hours(message, master)
```

Move the `from src.utils.work_hours import parse_hhmm` to the top of the file (grouped with the other imports from the same module).

- [ ] **Step 5: Linters + tests**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy src/ tests/
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" uv run pytest tests/ -v
```

Expected: all pass. (No new DB tests — settings is tested manually via Telegram; the parsing logic is already covered in Task 8.)

- [ ] **Step 6: Smoke-test**

```bash
docker compose build app && docker compose up -d app
```

In Telegram:
- `⚙️ Настройки → Часы работы` → list of 7 days, all show "выходной" (fresh install).
- Tap `Пн` → prompt "Начало…" with inline `Выходной` button.
- Send `10:00` → prompt "Конец…". Send `19:00` → list refreshes, `Пн: 10:00–19:00`.
- Tap `Вт` → type `abc` → bot replies "Не разобрал". Send `09:00` → "Конец". Send `09:00` → "Конец должен быть позже начала".
- Tap `Ср` → bot prompts → tap `Выходной` button → day stays as выходной, list refreshes.
- Tap `Готово` → toast "Сохранено."

Verify persistence:

```bash
docker compose exec postgres psql -U botik -d botik \
  -c "SELECT tg_id, work_hours FROM masters;"
```

Expected: JSONB like `{"mon": [["10:00","19:00"]]}`.

- [ ] **Step 7: Commit**

```bash
git add src/fsm/work_hours.py src/callback_data/settings.py src/keyboards/settings.py src/handlers/master/settings.py
git commit -m "feat(settings): work_hours FSM with HH:MM parsing and day-off toggle"
```

---

## Task 10: Epic 2 acceptance + tag

- [ ] **Step 1: Run everything one last time**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/ tests/
DATABASE_URL="postgresql+asyncpg://botik:botik@localhost:5432/botik" \
  uv run pytest tests/ -v --cov=src --cov-report=term-missing
```

Expected: clean on lint, all tests pass. Coverage targets (from CLAUDE.md):
- `src/utils/work_hours.py` should show ≥95% (pure function, unit-tested).
- `src/repositories/*.py` should show ≥90%.
- Handlers are smoke-tested manually — coverage will be lower, that's expected for this epic.

- [ ] **Step 2: Final Docker smoke**

```bash
docker compose ps
```

Expected: `postgres` healthy, `redis` healthy, `app` running.

In Telegram, walk the full master flow:
1. If you've already registered in earlier smoke tests, that's fine — skip step 3, step 4 works directly. Otherwise: fresh admin tg_id, `/start` → name → phone → menu.
2. `/services` → add 2 services (e.g. "Чистка" 45 min, "Пломба" 30 min).
3. Edit one service (new duration). Toggle one active. Confirm list updates.
4. `⚙️ Настройки → Часы работы` → set Mon–Fri hours, Sat as выходной, Sun as выходной. Confirm persistence in psql.

- [ ] **Step 3: Commit any final cleanup (if needed)**

If smoke-testing revealed nothing, skip. Otherwise fix + commit.

- [ ] **Step 4: Tag the milestone**

```bash
git tag -a v0.2.0-epic-2 -m "Epic 2 complete: master registration, services CRUD, work hours"
git push origin main
git push origin v0.2.0-epic-2
```

---

## Epic 2 deliverables

- `/start` dispatcher: registers new admins via FSM, welcomes existing masters with main menu, politely rejects unknown tg_ids.
- Main menu (reply keyboard) + `/settings` inline menu.
- `/services` list, add/edit/delete, active-toggle (soft delete).
- `⚙️ Настройки → Часы работы`: per-weekday single interval, validated HH:MM, выходной button.
- `MasterRepository` + `ServiceRepository` with tests against real Postgres.
- Pure `src/utils/work_hours.py` with parsing + immutable day setters (unit-tested).
- RedisStorage for FSM (project rule).

## What comes next (NOT in this plan)

- Breaks sub-menu (`⚙️ Настройки → Перерывы`) — same FSM shape as work hours, different field. Easy follow-up.
- Epic 3: pure `calculate_free_slots` + `BookingService`.
- Epic 4: client-side booking flow with inline calendar.
- Fluent-based i18n replacing `src/strings.py`.
