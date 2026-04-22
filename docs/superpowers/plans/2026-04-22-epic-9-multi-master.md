# Epic 9: Multi-Master v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Превратить single-tenant бота в shared-instance multi-master платформу с инвайт-регистрацией мастеров, публичным каталогом и soft-block модерацией.

**Architecture:** Расширяем `masters` (slug/specialty/is_public/blocked_at) + добавляем `invites`. Deep-link'и: `/start invite_<code>` — регистрация мастера, `/start master_<slug>` — booking у конкретного мастера, `/start` без payload — каталог. Фикс `UserMiddleware` (убираем клиентский lookup — падает на multi-master). Admin-menu reply-keyboard. Button-first UX: каждая новая команда имеет кнопочный путь.

**Tech Stack:** Python 3.12 async, aiogram 3.x, SQLAlchemy 2.0, Alembic, Postgres 16, Redis 7, APScheduler, pytest, mypy strict, ruff.

**Спека:** [`docs/superpowers/specs/2026-04-22-epic-9-multi-master-design.md`](../specs/2026-04-22-epic-9-multi-master-design.md)

---

## Файловая структура

| Файл | Статус | Назначение |
|------|--------|------------|
| `migrations/versions/0003_epic9_multi_master.py` | NEW | Миграция: колонки masters + таблица invites + data-migration для существующего мастера |
| `src/db/models.py` | MODIFY | Расширить `Master` (slug, specialty_text, is_public, blocked_at) + добавить `Invite` |
| `src/exceptions.py` | MODIFY | `SlugTaken`, `InvalidSlug`, `ReservedSlug`, `InviteNotFound`, `InviteExpired`, `InviteAlreadyUsed`, `MasterBlocked` |
| `src/services/slug.py` | NEW | `SlugService` — транслит + генерация + валидация |
| `src/services/invite.py` | NEW | `InviteService` — создание и redeem инвайтов |
| `src/services/master_registration.py` | NEW | `MasterRegistrationService` — транзакционная регистрация |
| `src/services/moderation.py` | NEW | `ModerationService` — block/unblock + bulk-reject |
| `src/repositories/masters.py` | MODIFY | `by_slug`, `list_public`, `update_slug`, `set_blocked`, `set_specialty` |
| `src/repositories/invites.py` | NEW | CRUD для invites |
| `src/repositories/appointments.py` | MODIFY | `bulk_reject_pending_for_master` |
| `src/callback_data/registration.py` | NEW | `SpecialtyHintCallback`, `SlugConfirmCallback` |
| `src/callback_data/admin.py` | NEW | `AdminMasterCallback`, `BlockCallback` |
| `src/callback_data/catalog.py` | NEW | `CatalogMasterCallback` |
| `src/keyboards/common.py` | MODIFY | Добавить `🔗 Моя ссылка` в `main_menu()` |
| `src/keyboards/admin.py` | NEW | `admin_menu()` + `masters_list_kb()` + `block_toggle_kb()` |
| `src/keyboards/registration.py` | NEW | `specialty_hints_kb()` + `slug_confirm_kb()` |
| `src/keyboards/settings.py` | MODIFY | Добавить Профиль / Мои инвайты / Пригласить мастера |
| `src/keyboards/catalog.py` | NEW | `catalog_kb(masters)` |
| `src/fsm/master_register.py` | MODIFY | Добавить `waiting_specialty`, `waiting_slug_confirm`, `waiting_custom_slug` |
| `src/middlewares/user.py` | MODIFY | Убрать клиентский `session.scalar` lookup |
| `src/middlewares/admin.py` | NEW | Проставляет `data["is_admin"]` по ADMIN_TG_IDS |
| `src/handlers/master/start.py` | MODIFY | Парсить `/start invite_<code>` + блок-guard |
| `src/handlers/master/menu.py` | MODIFY | `handle_my_link`, `handle_my_invites` button-dispatch |
| `src/handlers/master/my_link.py` | NEW | `cmd_mylink` |
| `src/handlers/master/my_invites.py` | NEW | `cmd_myinvites` |
| `src/handlers/master/new_invite.py` | NEW | `cmd_new_invite` + settings-кнопка |
| `src/handlers/master/registration.py` | NEW | Specialty/slug FSM steps |
| `src/handlers/master/profile.py` | NEW | Редактор профиля (имя/специальность/slug) |
| `src/handlers/master/settings.py` | MODIFY | Добавить 3 новых раздела |
| `src/handlers/client/start.py` | MODIFY | Deep-link `master_<slug>` + каталог fallback |
| `src/handlers/client/catalog.py` | NEW | Рендер каталога + pick-handler |
| `src/handlers/admin/__init__.py` | NEW | Router подключения |
| `src/handlers/admin/menu.py` | NEW | Admin reply-keyboard dispatch |
| `src/handlers/admin/masters.py` | NEW | `/masters`, `/master <slug>` |
| `src/handlers/admin/stats.py` | NEW | `/stats` |
| `src/handlers/admin/invites_admin.py` | NEW | `/invites` (админский список всех) |
| `src/handlers/admin/moderation.py` | NEW | `/block`, `/unblock` + уведомления |
| `src/handlers/__init__.py` | MODIFY | Подключить admin_router (первым!) |
| `src/strings.py` | MODIFY | ~60 новых ключей (RU + HY) |
| `src/main.py` | MODIFY | Scope-aware `setup_bot_commands` (admin/master/client) |

---

## Выполнение

- После каждой задачи: `ruff check . && ruff format --check . && mypy src/ && pytest`.
- Commits — атомарные. На каждом шаге — либо тесты, либо код, либо один commit.
- Postgres + Redis должны быть запущены: `docker compose up -d postgres redis`.
- Начинай с feature-ветки: `git checkout -b feature/epic-9-multi-master`.

---

### Task 0: Подготовка ветки

**Files:** (ничего не правим)

- [ ] **Step 1: Создать feature-ветку**

Run: `git checkout -b feature/epic-9-multi-master && git status`
Expected: `On branch feature/epic-9-multi-master, nothing to commit`

- [ ] **Step 2: Поднять локальные зависимости для тестов**

Run: `docker compose up -d postgres redis && sleep 3 && docker compose ps`
Expected: postgres и redis в статусе `Up` / `healthy`

- [ ] **Step 3: Baseline: прогон всех тестов на main**

Run: `pytest -q`
Expected: все тесты зелёные (~330 прошлых). Это baseline, фиксируем.

---

### Task 1: Миграция 0003 — схема + data-migration

**Files:**
- Create: `migrations/versions/0003_epic9_multi_master.py`

- [ ] **Step 1: Создать файл миграции**

```python
"""epic 9: multi-master — masters columns + invites table + data migration

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-22 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns as nullable first
    op.add_column("masters", sa.Column("slug", sa.String(32), nullable=True))
    op.add_column(
        "masters",
        sa.Column("specialty_text", sa.String(200), nullable=False, server_default=""),
    )
    op.add_column(
        "masters",
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "masters",
        sa.Column("blocked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # 2. Data migration: generate slug for every existing master
    op.execute(
        """
        UPDATE masters
        SET slug = CONCAT(
            'master-',
            LPAD(TO_HEX((RANDOM() * 16777215)::int), 6, '0')
        )
        WHERE slug IS NULL
        """
    )

    # 3. Make slug NOT NULL and unique
    op.alter_column("masters", "slug", nullable=False)
    op.create_unique_constraint("uq_masters_slug", "masters", ["slug"])

    # 4. Catalog lookup index
    op.create_index(
        "ix_masters_catalog",
        "masters",
        ["is_public", "blocked_at"],
        postgresql_where=sa.text("blocked_at IS NULL AND is_public = true"),
    )

    # 5. Invites table
    op.create_table(
        "invites",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("created_by_tg_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("used_by_tg_id", sa.BigInteger(), nullable=True),
        sa.Column("used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "used_for_master_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("masters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "(used_by_tg_id IS NULL) = (used_at IS NULL) "
            "AND (used_at IS NULL) = (used_for_master_id IS NULL)",
            name="ck_invites_usage_tuple",
        ),
    )
    op.create_index("ix_invites_code", "invites", ["code"])
    op.create_index(
        "ix_invites_creator",
        "invites",
        ["created_by_tg_id", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_invites_creator", table_name="invites")
    op.drop_index("ix_invites_code", table_name="invites")
    op.drop_table("invites")

    op.drop_index("ix_masters_catalog", table_name="masters")
    op.drop_constraint("uq_masters_slug", "masters", type_="unique")
    op.drop_column("masters", "blocked_at")
    op.drop_column("masters", "is_public")
    op.drop_column("masters", "specialty_text")
    op.drop_column("masters", "slug")
```

- [ ] **Step 2: Прогнать миграцию на локальную БД**

Run: `alembic upgrade head`
Expected: `INFO  [alembic.runtime.migration] Running upgrade 0002 -> 0003`

- [ ] **Step 3: Проверить структуру**

Run: `docker compose exec postgres psql -U botik -d botik -c "\d masters" -c "\d invites"`
Expected: видим `slug`, `specialty_text`, `is_public`, `blocked_at` + таблица `invites` с колонками.

- [ ] **Step 4: Откат и повтор (проверка downgrade)**

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: обе команды проходят без ошибок.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/0003_epic9_multi_master.py
git commit -m "feat(db): migration 0003 — multi-master schema + invites table"
```

---

### Task 2: Обновить модели SQLAlchemy

**Files:**
- Modify: `src/db/models.py:26-52` (Master) + конец файла (add Invite)

- [ ] **Step 1: Написать тест на Invite-модель**

Файл: `tests/test_models_invite.py` (NEW)

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite


@pytest.mark.asyncio
async def test_invite_can_be_created(session: AsyncSession) -> None:
    invite = Invite(
        code="A7K2-X9MP",
        created_by_tg_id=111,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(invite)
    await session.commit()
    assert invite.id is not None
    assert invite.used_at is None
    assert invite.used_by_tg_id is None
    assert invite.used_for_master_id is None


@pytest.mark.asyncio
async def test_invite_code_is_unique(session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    i1 = Invite(
        code="DUP-CODE",
        created_by_tg_id=111,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(i1)
    await session.commit()

    i2 = Invite(
        code="DUP-CODE",
        created_by_tg_id=222,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(i2)
    with pytest.raises(IntegrityError):
        await session.commit()
```

- [ ] **Step 2: Запустить — ожидаем FAIL (модели нет)**

Run: `pytest tests/test_models_invite.py -v`
Expected: `ImportError: cannot import name 'Invite'`

- [ ] **Step 3: Добавить поля в Master и новую модель Invite**

В файле `src/db/models.py` заменить импорты (строка 7-21) добавить `DateTime`:

```python
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
```

В классе `Master` (перед полем `created_at`) добавить:

```python
    slug: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    specialty_text: Mapped[str] = mapped_column(
        String(200), nullable=False, server_default=""
    )
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    blocked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
```

Также добавить `__table_args__` в класс Master:

```python
    __table_args__ = (
        Index(
            "ix_masters_catalog",
            "is_public",
            "blocked_at",
            postgresql_where=text("blocked_at IS NULL AND is_public = true"),
        ),
    )
```

В конец файла добавить:

```python
class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint(
            "(used_by_tg_id IS NULL) = (used_at IS NULL) "
            "AND (used_at IS NULL) = (used_for_master_id IS NULL)",
            name="ck_invites_usage_tuple",
        ),
        Index("ix_invites_code", "code"),
        Index("ix_invites_creator", "created_by_tg_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    created_by_tg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False
    )
    used_by_tg_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    used_for_master_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("masters.id", ondelete="SET NULL"),
        nullable=True,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_models_invite.py -v`
Expected: PASS (2/2)

- [ ] **Step 5: Проверить что старые тесты не сломались**

Run: `pytest tests/test_repositories_masters.py -v`
Expected: все старые тесты мастеров PASS (metadata переживёт добавление колонок, так как тестовая БД пересоздаётся с `Base.metadata.create_all`).

- [ ] **Step 6: Commit**

```bash
git add src/db/models.py tests/test_models_invite.py
git commit -m "feat(db): Invite model + Master slug/specialty/is_public/blocked_at"
```

---

### Task 3: Exceptions — новые доменные исключения

**Files:**
- Modify: `src/exceptions.py`

- [ ] **Step 1: Написать тест на импортируемость**

Файл: `tests/test_exceptions_epic9.py` (NEW)

```python
from __future__ import annotations


def test_epic9_exceptions_exist() -> None:
    from src.exceptions import (
        InvalidSlug,
        InviteAlreadyUsed,
        InviteExpired,
        InviteNotFound,
        MasterBlocked,
        ReservedSlug,
        SlugTaken,
    )

    assert issubclass(SlugTaken, Exception)
    assert issubclass(InvalidSlug, Exception)
    assert issubclass(ReservedSlug, Exception)
    assert issubclass(InviteNotFound, Exception)
    assert issubclass(InviteExpired, Exception)
    assert issubclass(InviteAlreadyUsed, Exception)
    assert issubclass(MasterBlocked, Exception)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/test_exceptions_epic9.py -v`
Expected: ImportError.

- [ ] **Step 3: Добавить классы в `src/exceptions.py`**

В конец файла:

```python
class SlugTaken(Exception):
    """Raised when trying to set a slug that already exists."""


class InvalidSlug(Exception):
    """Raised when slug fails regex validation."""


class ReservedSlug(Exception):
    """Raised when slug matches a reserved value (admin, bot, api, ...)."""


class InviteNotFound(Exception):
    """Raised when invite code does not exist."""


class InviteExpired(Exception):
    """Raised when invite exists but is past expires_at."""


class InviteAlreadyUsed(Exception):
    """Raised when invite has used_at set."""


class MasterBlocked(Exception):
    """Raised when a blocked master attempts a master-scope action."""
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/test_exceptions_epic9.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/exceptions.py tests/test_exceptions_epic9.py
git commit -m "feat(exceptions): domain errors for Epic 9"
```

---

### Task 4: SlugService — валидация и генерация

**Files:**
- Create: `src/services/slug.py`
- Test: `tests/test_services_slug.py`

- [ ] **Step 1: Написать тесты**

```python
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.exceptions import InvalidSlug, ReservedSlug
from src.services.slug import SlugService


def test_validate_ok() -> None:
    SlugService.validate("anna-7f3c")
    SlugService.validate("dent123")
    SlugService.validate("a-b-c")


def test_validate_rejects_short() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("ab")


def test_validate_rejects_long() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("a" * 33)


def test_validate_rejects_uppercase() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("Anna")


def test_validate_rejects_leading_dash() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("-anna")


def test_validate_rejects_trailing_dash() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("anna-")


def test_validate_rejects_double_dash() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("a--b")


def test_validate_rejects_reserved() -> None:
    for bad in ["admin", "bot", "api", "grancvi", "master", "client", "invite"]:
        with pytest.raises(ReservedSlug):
            SlugService.validate(bad)


def test_transliterate_russian() -> None:
    assert SlugService.transliterate("Анна") == "anna"
    assert SlugService.transliterate("Арсен") == "arsen"
    assert SlugService.transliterate("Щёкин") == "shchyokin"


def test_transliterate_armenian() -> None:
    assert SlugService.transliterate("Արամ") == "aram"


def test_transliterate_empty_returns_master() -> None:
    assert SlugService.transliterate("") == "master"
    assert SlugService.transliterate("123") == "master"


@pytest.mark.asyncio
async def test_generate_default_unique(session: AsyncSession) -> None:
    svc = SlugService(session)
    slug = await svc.generate_default("Анна")
    assert slug.startswith("anna-")
    assert len(slug) >= 3

    master = Master(tg_id=1, name="Анна", slug=slug)
    session.add(master)
    await session.commit()

    slug2 = await svc.generate_default("Анна")
    assert slug2 != slug
    assert slug2.startswith("anna-")


@pytest.mark.asyncio
async def test_generate_default_fallback_after_collisions(session: AsyncSession) -> None:
    svc = SlugService(session)
    slug = await svc.generate_default("Анна")
    assert slug
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/test_services_slug.py -v`
Expected: `ModuleNotFoundError: No module named 'src.services.slug'`

- [ ] **Step 3: Реализовать `src/services/slug.py`**

```python
from __future__ import annotations

import re
import secrets
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.exceptions import InvalidSlug, ReservedSlug

_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MIN: Final[int] = 3
_MAX: Final[int] = 32

_RESERVED: Final[frozenset[str]] = frozenset(
    {"admin", "bot", "api", "grancvi", "master", "client", "invite"}
)

# Russian + Armenian to latin.
_RU_MAP: Final[dict[str, str]] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
_HY_MAP: Final[dict[str, str]] = {
    "ա": "a", "բ": "b", "գ": "g", "դ": "d", "ե": "e", "զ": "z", "է": "e",
    "ը": "y", "թ": "t", "ժ": "zh", "ի": "i", "լ": "l", "խ": "kh", "ծ": "ts",
    "կ": "k", "հ": "h", "ձ": "dz", "ղ": "gh", "ճ": "ch", "մ": "m", "յ": "y",
    "ն": "n", "շ": "sh", "ո": "o", "չ": "ch", "պ": "p", "ջ": "j", "ռ": "r",
    "ս": "s", "վ": "v", "տ": "t", "ր": "r", "ց": "ts", "ու": "u", "փ": "p",
    "ք": "k", "և": "ev", "օ": "o", "ֆ": "f",
}


class SlugService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def validate(slug: str) -> None:
        if slug in _RESERVED:
            raise ReservedSlug(slug)
        if not (_MIN <= len(slug) <= _MAX):
            raise InvalidSlug(f"length must be {_MIN}..{_MAX}")
        if not _SLUG_RE.match(slug):
            raise InvalidSlug("must match ^[a-z0-9]+(-[a-z0-9]+)*$")

    @staticmethod
    def transliterate(text: str) -> str:
        s = text.strip().lower()
        out: list[str] = []
        for ch in s:
            if ch in _RU_MAP:
                out.append(_RU_MAP[ch])
            elif ch in _HY_MAP:
                out.append(_HY_MAP[ch])
            elif ch.isascii() and ch.isalnum():
                out.append(ch)
            elif ch == " " or ch == "-":
                out.append("-")
            # else: drop
        cleaned = re.sub(r"-+", "-", "".join(out)).strip("-")
        # Must start with letter and be >=3 chars non-digit
        if not cleaned or cleaned.isdigit():
            return "master"
        # Ensure at least 3 chars prefix
        if len(cleaned) < 3:
            cleaned = cleaned + "-" + secrets.token_hex(2)
        return cleaned

    async def generate_default(self, first_name: str) -> str:
        base = self.transliterate(first_name)
        for _ in range(5):
            suffix = secrets.token_hex(2)  # 4 hex chars
            candidate = f"{base}-{suffix}"
            if len(candidate) > _MAX:
                candidate = candidate[:_MAX].rstrip("-")
            try:
                self.validate(candidate)
            except (InvalidSlug, ReservedSlug):
                continue
            existing = await self._session.scalar(
                select(Master).where(Master.slug == candidate)
            )
            if existing is None:
                return candidate
        # Fallback: master-<6hex>
        return f"master-{secrets.token_hex(3)}"
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/test_services_slug.py -v`
Expected: все 10+ тестов PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/slug.py tests/test_services_slug.py
git commit -m "feat(services): SlugService — transliterate + validate + generate"
```

---

### Task 5: InviteService — генерация кода и redeem

**Files:**
- Create: `src/services/invite.py`
- Create: `src/repositories/invites.py`
- Test: `tests/test_services_invite.py`
- Test: `tests/test_repositories_invites.py`

- [ ] **Step 1: Тест InviteRepository**

Файл `tests/test_repositories_invites.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.invites import InviteRepository


@pytest.mark.asyncio
async def test_create_invite(session: AsyncSession) -> None:
    repo = InviteRepository(session)
    invite = await repo.create(
        code="TEST-0001",
        created_by_tg_id=111,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    await session.commit()
    assert invite.code == "TEST-0001"
    assert invite.used_at is None


@pytest.mark.asyncio
async def test_by_code_found(session: AsyncSession) -> None:
    repo = InviteRepository(session)
    await repo.create(
        code="FIND-0001",
        created_by_tg_id=111,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    await session.commit()
    found = await repo.by_code("FIND-0001")
    assert found is not None
    assert found.code == "FIND-0001"


@pytest.mark.asyncio
async def test_by_code_not_found(session: AsyncSession) -> None:
    repo = InviteRepository(session)
    assert await repo.by_code("MISSING") is None


@pytest.mark.asyncio
async def test_list_by_creator_desc(session: AsyncSession) -> None:
    repo = InviteRepository(session)
    for i in range(3):
        await repo.create(
            code=f"CODE-{i:04d}",
            created_by_tg_id=777,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
    await session.commit()
    items = await repo.list_by_creator(777)
    assert len(items) == 3
```

- [ ] **Step 2: Реализовать `src/repositories/invites.py`**

```python
from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite


class InviteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        code: str,
        created_by_tg_id: int,
        expires_at: datetime,
    ) -> Invite:
        invite = Invite(
            code=code,
            created_by_tg_id=created_by_tg_id,
            expires_at=expires_at,
        )
        self._session.add(invite)
        await self._session.flush()
        return invite

    async def by_code(self, code: str) -> Invite | None:
        return cast(
            Invite | None,
            await self._session.scalar(select(Invite).where(Invite.code == code)),
        )

    async def mark_used(
        self,
        *,
        code: str,
        used_by_tg_id: int,
        master_id: UUID,
        used_at: datetime,
    ) -> None:
        invite = await self.by_code(code)
        if invite is None:
            return
        invite.used_by_tg_id = used_by_tg_id
        invite.used_for_master_id = master_id
        invite.used_at = used_at

    async def list_by_creator(self, tg_id: int) -> list[Invite]:
        stmt = (
            select(Invite)
            .where(Invite.created_by_tg_id == tg_id)
            .order_by(Invite.created_at.desc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_all(self) -> list[Invite]:
        stmt = select(Invite).order_by(Invite.created_at.desc())
        result = await self._session.scalars(stmt)
        return list(result.all())
```

- [ ] **Step 3: Тест InviteService**

Файл `tests/test_services_invite.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master
from src.exceptions import InviteAlreadyUsed, InviteExpired, InviteNotFound
from src.services.invite import InviteService


def test_generate_code_format() -> None:
    code = InviteService.generate_code()
    # Format XXXX-XXXX with alphabet A-Z (no I/O) + digits 2-9
    import re
    assert re.match(r"^[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}$", code)


def test_generate_code_unique() -> None:
    seen = {InviteService.generate_code() for _ in range(100)}
    assert len(seen) == 100  # effectively


@pytest.mark.asyncio
async def test_create_invite_persists(session: AsyncSession) -> None:
    svc = InviteService(session)
    invite = await svc.create_invite(actor_tg_id=111)
    await session.commit()
    assert invite.created_by_tg_id == 111
    assert invite.expires_at > datetime.now(timezone.utc) + timedelta(days=6)


@pytest.mark.asyncio
async def test_redeem_success(session: AsyncSession) -> None:
    svc = InviteService(session)
    invite = await svc.create_invite(actor_tg_id=111)
    await session.commit()
    master = Master(tg_id=222, name="Arman", slug="arman-abcd")
    session.add(master)
    await session.flush()
    used = await svc.redeem(code=invite.code, tg_id=222, master_id=master.id)
    await session.commit()
    assert used.used_by_tg_id == 222
    assert used.used_for_master_id == master.id


@pytest.mark.asyncio
async def test_redeem_not_found(session: AsyncSession) -> None:
    svc = InviteService(session)
    with pytest.raises(InviteNotFound):
        await svc.redeem(code="MISSING", tg_id=111, master_id=uuid4())


@pytest.mark.asyncio
async def test_redeem_expired(session: AsyncSession) -> None:
    svc = InviteService(session)
    invite = Invite(
        code="EXP-0001",
        created_by_tg_id=1,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    session.add(invite)
    await session.commit()
    with pytest.raises(InviteExpired):
        await svc.redeem(code="EXP-0001", tg_id=222, master_id=uuid4())


@pytest.mark.asyncio
async def test_redeem_already_used(session: AsyncSession) -> None:
    svc = InviteService(session)
    master = Master(tg_id=333, name="X", slug="x-aaaa")
    session.add(master)
    await session.flush()
    invite = Invite(
        code="USED-0001",
        created_by_tg_id=1,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        used_by_tg_id=333,
        used_for_master_id=master.id,
        used_at=datetime.now(timezone.utc),
    )
    session.add(invite)
    await session.commit()
    with pytest.raises(InviteAlreadyUsed):
        await svc.redeem(code="USED-0001", tg_id=333, master_id=master.id)
```

- [ ] **Step 4: Реализовать `src/services/invite.py`**

```python
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite
from src.exceptions import InviteAlreadyUsed, InviteExpired, InviteNotFound
from src.repositories.invites import InviteRepository

_ALPHABET: Final[str] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I,O,0,1
_TTL_DAYS: Final[int] = 7


class InviteService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = InviteRepository(session)

    @staticmethod
    def generate_code() -> str:
        left = "".join(secrets.choice(_ALPHABET) for _ in range(4))
        right = "".join(secrets.choice(_ALPHABET) for _ in range(4))
        return f"{left}-{right}"

    async def create_invite(self, *, actor_tg_id: int) -> Invite:
        code = self.generate_code()
        expires = datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS)
        return await self._repo.create(
            code=code, created_by_tg_id=actor_tg_id, expires_at=expires
        )

    async def redeem(self, *, code: str, tg_id: int, master_id: UUID) -> Invite:
        invite = await self._repo.by_code(code)
        if invite is None:
            raise InviteNotFound(code)
        if invite.used_at is not None:
            raise InviteAlreadyUsed(code)
        if invite.expires_at <= datetime.now(timezone.utc):
            raise InviteExpired(code)
        await self._repo.mark_used(
            code=code,
            used_by_tg_id=tg_id,
            master_id=master_id,
            used_at=datetime.now(timezone.utc),
        )
        await self._session.flush()
        refreshed = await self._repo.by_code(code)
        assert refreshed is not None
        return refreshed
```

- [ ] **Step 5: Run — expect PASS**

Run: `pytest tests/test_repositories_invites.py tests/test_services_invite.py -v`
Expected: все PASS.

- [ ] **Step 6: Commit**

```bash
git add src/services/invite.py src/repositories/invites.py \
  tests/test_services_invite.py tests/test_repositories_invites.py
git commit -m "feat(invite): repo + service for invite creation and redemption"
```

---

### Task 6: Расширить MasterRepository

**Files:**
- Modify: `src/repositories/masters.py`
- Test: `tests/test_repositories_masters_epic9.py` (NEW)

- [ ] **Step 1: Написать тесты**

```python
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.repositories.masters import MasterRepository


@pytest.mark.asyncio
async def test_by_slug_found(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="anna-0001")
    session.add(m)
    await session.commit()
    repo = MasterRepository(session)
    found = await repo.by_slug("anna-0001")
    assert found is not None and found.tg_id == 1


@pytest.mark.asyncio
async def test_by_slug_missing(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    assert await repo.by_slug("nope") is None


@pytest.mark.asyncio
async def test_list_public_excludes_blocked(session: AsyncSession) -> None:
    session.add(Master(tg_id=1, name="A", slug="a-0001", is_public=True))
    session.add(
        Master(
            tg_id=2, name="B", slug="b-0001",
            is_public=True, blocked_at=datetime.now(timezone.utc),
        )
    )
    session.add(Master(tg_id=3, name="C", slug="c-0001", is_public=False))
    session.add(Master(tg_id=4, name="D", slug="d-0001", is_public=True))
    await session.commit()
    repo = MasterRepository(session)
    items = await repo.list_public()
    slugs = [m.slug for m in items]
    assert "a-0001" in slugs
    assert "d-0001" in slugs
    assert "b-0001" not in slugs
    assert "c-0001" not in slugs


@pytest.mark.asyncio
async def test_set_blocked_toggle(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="a-0001")
    session.add(m)
    await session.commit()
    repo = MasterRepository(session)
    await repo.set_blocked(m.id, blocked=True)
    await session.commit()
    await session.refresh(m)
    assert m.blocked_at is not None

    await repo.set_blocked(m.id, blocked=False)
    await session.commit()
    await session.refresh(m)
    assert m.blocked_at is None


@pytest.mark.asyncio
async def test_update_slug_ok(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="a-0001")
    session.add(m)
    await session.commit()
    repo = MasterRepository(session)
    await repo.update_slug(m.id, "new-slug")
    await session.commit()
    await session.refresh(m)
    assert m.slug == "new-slug"


@pytest.mark.asyncio
async def test_update_slug_collision(session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    m1 = Master(tg_id=1, name="A", slug="a-0001")
    m2 = Master(tg_id=2, name="B", slug="b-0001")
    session.add_all([m1, m2])
    await session.commit()
    repo = MasterRepository(session)
    await repo.update_slug(m2.id, "a-0001")
    with pytest.raises(IntegrityError):
        await session.commit()
```

- [ ] **Step 2: Добавить методы в `src/repositories/masters.py`**

В конец класса:

```python
    async def by_slug(self, slug: str) -> Master | None:
        return cast(
            Master | None,
            await self._session.scalar(select(Master).where(Master.slug == slug)),
        )

    async def list_public(self) -> list[Master]:
        stmt = (
            select(Master)
            .where(Master.is_public.is_(True), Master.blocked_at.is_(None))
            .order_by(Master.created_at.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_all(self) -> list[Master]:
        stmt = select(Master).order_by(Master.created_at.asc())
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def update_slug(self, master_id: Any, slug: str) -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.slug = slug

    async def update_specialty(self, master_id: Any, specialty: str) -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.specialty_text = specialty

    async def update_name(self, master_id: Any, name: str) -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.name = name

    async def set_blocked(self, master_id: Any, *, blocked: bool) -> None:
        from datetime import datetime, timezone
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.blocked_at = datetime.now(timezone.utc) if blocked else None
```

Также добавить в импорт (в начале файла): `from datetime import datetime, timezone` → лучше локальный импорт в методе (см. выше).

- [ ] **Step 3: Run — expect PASS**

Run: `pytest tests/test_repositories_masters_epic9.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/repositories/masters.py tests/test_repositories_masters_epic9.py
git commit -m "feat(repo): by_slug/list_public/set_blocked/update_* on MasterRepository"
```

---

### Task 7: AppointmentRepository — bulk reject pending for master

**Files:**
- Modify: `src/repositories/appointments.py`
- Test: `tests/test_repositories_appointments_epic9.py` (NEW)

- [ ] **Step 1: Прочитать существующий файл, найти точку вставки**

Run: `grep -n "class AppointmentRepository\|async def" src/repositories/appointments.py`
Expected: список существующих методов, вставить в конец класса.

- [ ] **Step 2: Написать тест**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.repositories.appointments import AppointmentRepository


@pytest.mark.asyncio
async def test_bulk_reject_pending_only(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="a-0001")
    session.add(m)
    await session.flush()
    svc = Service(master_id=m.id, name="cut", duration_min=30)
    session.add(svc)
    cli = Client(master_id=m.id, name="C", phone="+37499000001")
    session.add(cli)
    await session.flush()

    now = datetime.now(timezone.utc)
    pending = Appointment(
        master_id=m.id, client_id=cli.id, service_id=svc.id,
        start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=2),
        status="pending", source="client_request",
    )
    confirmed = Appointment(
        master_id=m.id, client_id=cli.id, service_id=svc.id,
        start_at=now + timedelta(hours=3), end_at=now + timedelta(hours=4),
        status="confirmed", source="client_request",
    )
    session.add_all([pending, confirmed])
    await session.commit()

    repo = AppointmentRepository(session)
    affected = await repo.bulk_reject_pending_for_master(m.id, reason="master_blocked")
    await session.commit()

    await session.refresh(pending)
    await session.refresh(confirmed)
    assert pending.status == "rejected"
    assert confirmed.status == "confirmed"
    assert len(affected) == 1
    assert affected[0].id == pending.id


@pytest.mark.asyncio
async def test_bulk_reject_other_master_untouched(session: AsyncSession) -> None:
    m1 = Master(tg_id=1, name="A", slug="a-0001")
    m2 = Master(tg_id=2, name="B", slug="b-0001")
    session.add_all([m1, m2])
    await session.flush()
    svc1 = Service(master_id=m1.id, name="cut", duration_min=30)
    svc2 = Service(master_id=m2.id, name="cut", duration_min=30)
    cli1 = Client(master_id=m1.id, name="C1", phone="+111")
    cli2 = Client(master_id=m2.id, name="C2", phone="+222")
    session.add_all([svc1, svc2, cli1, cli2])
    await session.flush()

    now = datetime.now(timezone.utc)
    a1 = Appointment(
        master_id=m1.id, client_id=cli1.id, service_id=svc1.id,
        start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=2),
        status="pending", source="client_request",
    )
    a2 = Appointment(
        master_id=m2.id, client_id=cli2.id, service_id=svc2.id,
        start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=2),
        status="pending", source="client_request",
    )
    session.add_all([a1, a2])
    await session.commit()

    repo = AppointmentRepository(session)
    await repo.bulk_reject_pending_for_master(m1.id, reason="master_blocked")
    await session.commit()

    await session.refresh(a1)
    await session.refresh(a2)
    assert a1.status == "rejected"
    assert a2.status == "pending"
```

- [ ] **Step 3: Реализовать метод**

Добавить в `src/repositories/appointments.py` в класс:

```python
    async def bulk_reject_pending_for_master(
        self,
        master_id: Any,
        *,
        reason: str,
    ) -> list[Appointment]:
        """Reject all pending appointments for a master; return the rejected rows."""
        stmt = (
            select(Appointment)
            .where(Appointment.master_id == master_id, Appointment.status == "pending")
        )
        result = await self._session.scalars(stmt)
        rows = list(result.all())
        now = datetime.now(timezone.utc)
        for appt in rows:
            appt.status = "rejected"
            appt.cancelled_at = now
            appt.cancelled_by = "system"
            appt.comment = (appt.comment or "") + f" [{reason}]"
        return rows
```

Проверь импорты: нужны `datetime`, `timezone`, `select`, `Any`, `Appointment`. Если отсутствуют — добавь.

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/test_repositories_appointments_epic9.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/repositories/appointments.py tests/test_repositories_appointments_epic9.py
git commit -m "feat(repo): bulk_reject_pending_for_master for soft-block"
```

---

### Task 8: Строки (RU + HY) для всех новых сообщений

**Files:**
- Modify: `src/strings.py`

- [ ] **Step 1: Написать тест на наличие ключей**

Файл `tests/test_strings_epic9_keys.py` (NEW):

```python
from __future__ import annotations

from src.strings import get_bundle

REQUIRED_KEYS = [
    # Invite / registration
    "INVITE_CREATED_FMT",           # "Инвайт создан.\nКод: {code}\nСсылка: {link}"
    "INVITE_EXPIRES_FMT",           # "Действителен до {date}"
    "INVITE_NOT_FOUND",
    "INVITE_EXPIRED",
    "INVITE_ALREADY_USED",
    "INVITE_ALREADY_MASTER",
    "REGISTER_ASK_SPECIALTY",
    "REGISTER_SPECIALTY_HINT_HAIR",
    "REGISTER_SPECIALTY_HINT_DENTIST",
    "REGISTER_SPECIALTY_HINT_NAILS",
    "REGISTER_SPECIALTY_HINT_COSMETOLOGIST",
    "REGISTER_SPECIALTY_HINT_CUSTOM",
    "REGISTER_SLUG_CONFIRM_FMT",    # "Ваш адрес: {slug}\nПодтвердить или изменить?"
    "REGISTER_SLUG_USE_BTN",
    "REGISTER_SLUG_CHANGE_BTN",
    "REGISTER_ASK_CUSTOM_SLUG",
    "REGISTER_SLUG_TAKEN",
    "REGISTER_SLUG_INVALID",
    "REGISTER_SLUG_RESERVED",
    # My link / invites
    "MAIN_MENU_MY_LINK",
    "MY_LINK_MSG_FMT",              # "Ваша ссылка: {link}\nПоделитесь с клиентами."
    "MY_INVITES_EMPTY",
    "MY_INVITES_HEADER",
    "MY_INVITES_ITEM_FMT",          # "{code} · {status} · до {expires}"
    "MY_INVITES_STATUS_ACTIVE",
    "MY_INVITES_STATUS_USED",
    "MY_INVITES_STATUS_EXPIRED",
    "NEW_INVITE_BTN",
    "SETTINGS_BTN_MY_LINK",
    "SETTINGS_BTN_MY_INVITES",
    "SETTINGS_BTN_NEW_INVITE",
    "SETTINGS_BTN_PROFILE",
    "SETTINGS_BTN_ADMIN",
    # Profile editor
    "PROFILE_MENU_TITLE",
    "PROFILE_BTN_NAME",
    "PROFILE_BTN_SPECIALTY",
    "PROFILE_BTN_SLUG",
    "PROFILE_ASK_NEW_NAME",
    "PROFILE_ASK_NEW_SPECIALTY",
    "PROFILE_ASK_NEW_SLUG",
    "PROFILE_UPDATED",
    # Client catalog
    "CLIENT_CATALOG_HEADER",
    "CLIENT_CATALOG_EMPTY",
    "CLIENT_CATALOG_CARD_FMT",      # "👤 {name} — {specialty}"
    "CLIENT_CATALOG_PICK_BTN",
    "CLIENT_MASTER_NOT_FOUND",
    "CLIENT_MASTER_CARD_FMT",
    "CLIENT_BOOK_HERE_BTN",
    # Block
    "MASTER_BLOCKED_BANNER",
    "CLIENT_APPT_REJECTED_BLOCK",
    # Admin
    "ADMIN_MENU_TITLE",
    "ADMIN_MENU_MASTERS",
    "ADMIN_MENU_STATS",
    "ADMIN_MENU_INVITES",
    "ADMIN_MENU_MODERATION",
    "ADMIN_MENU_BACK",
    "ADMIN_MASTERS_HEADER",
    "ADMIN_MASTERS_EMPTY",
    "ADMIN_MASTER_ITEM_FMT",        # "{slug} · {name} · {status}"
    "ADMIN_MASTER_STATUS_ACTIVE",
    "ADMIN_MASTER_STATUS_BLOCKED",
    "ADMIN_BLOCK_BTN",
    "ADMIN_UNBLOCK_BTN",
    "ADMIN_BLOCK_DONE_FMT",         # "Мастер {slug} заблокирован. Отменено pending: {n}"
    "ADMIN_UNBLOCK_DONE_FMT",
    "ADMIN_STATS_FMT",              # full block
    "ADMIN_INVITES_HEADER",
    "ADMIN_INVITE_ITEM_FMT",
    "ADMIN_MASTER_NOT_FOUND",
]


def test_ru_bundle_has_all_epic9_keys() -> None:
    ru = get_bundle("ru")
    missing = [k for k in REQUIRED_KEYS if not hasattr(ru, k)]
    assert not missing, f"Missing RU keys: {missing}"


def test_hy_bundle_has_all_epic9_keys() -> None:
    hy = get_bundle("hy")
    missing = [k for k in REQUIRED_KEYS if not hasattr(hy, k)]
    assert not missing, f"Missing HY keys: {missing}"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/test_strings_epic9_keys.py -v`
Expected: FAIL, список недостающих ключей.

- [ ] **Step 3: Добавить ключи в `src/strings.py`**

В `_RU` словарь (пример значений, RU):

```python
    # --- Epic 9: multi-master ---
    "INVITE_CREATED_FMT": "Инвайт создан.\n\nКод: `{code}`\nСсылка: {link}\n\nДействителен до: {expires}",
    "INVITE_EXPIRES_FMT": "до {date}",
    "INVITE_NOT_FOUND": "Код инвайта не найден.",
    "INVITE_EXPIRED": "Код инвайта истёк. Попросите новый.",
    "INVITE_ALREADY_USED": "Этот код уже использован.",
    "INVITE_ALREADY_MASTER": "Вы уже зарегистрированы как мастер.",
    "REGISTER_ASK_SPECIALTY": "Кто вы по специальности? Нажмите кнопку-подсказку или напишите своё:",
    "REGISTER_SPECIALTY_HINT_HAIR": "💈 Парикмахер",
    "REGISTER_SPECIALTY_HINT_DENTIST": "🦷 Стоматолог",
    "REGISTER_SPECIALTY_HINT_NAILS": "💅 Мастер маникюра",
    "REGISTER_SPECIALTY_HINT_COSMETOLOGIST": "💆 Косметолог",
    "REGISTER_SPECIALTY_HINT_CUSTOM": "✏️ Своё",
    "REGISTER_SLUG_CONFIRM_FMT": "Ваша ссылка будет:\nt.me/grancvi_bot?start=master_{slug}\n\nИспользовать?",
    "REGISTER_SLUG_USE_BTN": "✅ Использовать",
    "REGISTER_SLUG_CHANGE_BTN": "✏️ Изменить",
    "REGISTER_ASK_CUSTOM_SLUG": "Введите адрес (только латиница, цифры, дефис, 3–32 символа):",
    "REGISTER_SLUG_TAKEN": "Этот адрес уже занят. Попробуйте другой.",
    "REGISTER_SLUG_INVALID": "Адрес должен быть из латиницы, цифр и дефисов (3–32).",
    "REGISTER_SLUG_RESERVED": "Этот адрес зарезервирован. Выберите другой.",
    "MAIN_MENU_MY_LINK": "🔗 Моя ссылка",
    "MY_LINK_MSG_FMT": "Ваша ссылка для клиентов:\n{link}\n\nПоделитесь ею в соцсетях или с клиентами напрямую.",
    "MY_INVITES_EMPTY": "Вы пока не создавали инвайтов.",
    "MY_INVITES_HEADER": "Ваши инвайты:",
    "MY_INVITES_ITEM_FMT": "`{code}` · {status} · {expires}",
    "MY_INVITES_STATUS_ACTIVE": "активен",
    "MY_INVITES_STATUS_USED": "использован",
    "MY_INVITES_STATUS_EXPIRED": "просрочен",
    "NEW_INVITE_BTN": "➕ Пригласить мастера",
    "SETTINGS_BTN_MY_LINK": "🔗 Моя ссылка",
    "SETTINGS_BTN_MY_INVITES": "📨 Мои инвайты",
    "SETTINGS_BTN_NEW_INVITE": "➕ Пригласить мастера",
    "SETTINGS_BTN_PROFILE": "👤 Мой профиль",
    "SETTINGS_BTN_ADMIN": "🛠 Админ",
    "PROFILE_MENU_TITLE": "Что изменить?",
    "PROFILE_BTN_NAME": "✏️ Имя",
    "PROFILE_BTN_SPECIALTY": "✏️ Специальность",
    "PROFILE_BTN_SLUG": "✏️ Адрес (slug)",
    "PROFILE_ASK_NEW_NAME": "Введите новое имя:",
    "PROFILE_ASK_NEW_SPECIALTY": "Введите специальность:",
    "PROFILE_ASK_NEW_SLUG": "Введите новый адрес (3–32 символа, a-z0-9-):",
    "PROFILE_UPDATED": "Готово ✅",
    "CLIENT_CATALOG_HEADER": "Выберите мастера:",
    "CLIENT_CATALOG_EMPTY": "Мастера пока не зарегистрированы.",
    "CLIENT_CATALOG_CARD_FMT": "👤 {name} — {specialty}",
    "CLIENT_CATALOG_PICK_BTN": "📅 Записаться",
    "CLIENT_MASTER_NOT_FOUND": "Мастер не найден.",
    "CLIENT_MASTER_CARD_FMT": "👤 {name}\n{specialty}",
    "CLIENT_BOOK_HERE_BTN": "📅 Записаться",
    "MASTER_BLOCKED_BANNER": "⛔ Ваш кабинет временно заблокирован администратором.",
    "CLIENT_APPT_REJECTED_BLOCK": "К сожалению, мастер временно недоступен. Ваша заявка отменена.",
    "ADMIN_MENU_TITLE": "Админ-меню:",
    "ADMIN_MENU_MASTERS": "👥 Мастера",
    "ADMIN_MENU_STATS": "📊 Статистика",
    "ADMIN_MENU_INVITES": "📨 Инвайты",
    "ADMIN_MENU_MODERATION": "🛠 Модерация",
    "ADMIN_MENU_BACK": "⬅️ В главное меню",
    "ADMIN_MASTERS_HEADER": "Все мастера:",
    "ADMIN_MASTERS_EMPTY": "Мастеров пока нет.",
    "ADMIN_MASTER_ITEM_FMT": "`{slug}` · {name} · {status}",
    "ADMIN_MASTER_STATUS_ACTIVE": "активен",
    "ADMIN_MASTER_STATUS_BLOCKED": "заблокирован",
    "ADMIN_BLOCK_BTN": "🚫 Заблокировать",
    "ADMIN_UNBLOCK_BTN": "✅ Разблокировать",
    "ADMIN_BLOCK_DONE_FMT": "Мастер {slug} заблокирован. Отменено pending: {n}.",
    "ADMIN_UNBLOCK_DONE_FMT": "Мастер {slug} разблокирован.",
    "ADMIN_STATS_FMT": (
        "📊 Статистика\n\n"
        "Мастера: {masters_active} активных / {masters_blocked} заблокированных\n"
        "Клиентов (уникальных): {clients}\n"
        "Записей за 7 дней: {appt_7d}\n"
        "Записей за 30 дней: {appt_30d}"
    ),
    "ADMIN_INVITES_HEADER": "Все инвайты:",
    "ADMIN_INVITE_ITEM_FMT": "`{code}` · {status} · by {creator_tg_id}",
    "ADMIN_MASTER_NOT_FOUND": "Мастер с таким slug не найден.",
```

В `_HY` — аналогично, армянский перевод. Пример:

```python
    "INVITE_CREATED_FMT": "Հրավերը ստեղծված է։\n\nԿոդ՝ `{code}`\nՀղում՝ {link}\n\nՎավերական մինչ՝ {expires}",
    "INVITE_EXPIRES_FMT": "մինչ {date}",
    "INVITE_NOT_FOUND": "Հրավերի կոդը չի գտնվել։",
    "INVITE_EXPIRED": "Հրավերի կոդը ժամկետանց է։ Խնդրեք նոր կոդ։",
    "INVITE_ALREADY_USED": "Այս կոդն արդեն օգտագործվել է։",
    "INVITE_ALREADY_MASTER": "Դուք արդեն գրանցված եք որպես վարպետ։",
    "REGISTER_ASK_SPECIALTY": "Ի՞նչ մասնագիտություն ունեք։ Սեղմեք կոճակ կամ գրեք ձերը․",
    "REGISTER_SPECIALTY_HINT_HAIR": "💈 Վարսահարդար",
    "REGISTER_SPECIALTY_HINT_DENTIST": "🦷 Ատամնաբույժ",
    "REGISTER_SPECIALTY_HINT_NAILS": "💅 Մատնահարդար",
    "REGISTER_SPECIALTY_HINT_COSMETOLOGIST": "💆 Կոսմետոլոգ",
    "REGISTER_SPECIALTY_HINT_CUSTOM": "✏️ Այլ",
    "REGISTER_SLUG_CONFIRM_FMT": "Ձեր հղումը կլինի՝\nt.me/grancvi_bot?start=master_{slug}\n\nՕգտագործե՞լ։",
    "REGISTER_SLUG_USE_BTN": "✅ Օգտագործել",
    "REGISTER_SLUG_CHANGE_BTN": "✏️ Փոխել",
    "REGISTER_ASK_CUSTOM_SLUG": "Մուտքագրեք հասցեն (միայն լատինատառ, թվեր, գծիկ, 3–32 սիմվոլ)․",
    "REGISTER_SLUG_TAKEN": "Այս հասցեն զբաղված է։ Ընտրեք այլը։",
    "REGISTER_SLUG_INVALID": "Հասցեն պետք է բաղկացած լինի լատինատառից, թվերից և գծիկներից (3–32)։",
    "REGISTER_SLUG_RESERVED": "Այս հասցեն ամրագրված է։ Ընտրեք այլը։",
    "MAIN_MENU_MY_LINK": "🔗 Իմ հղումը",
    "MY_LINK_MSG_FMT": "Ձեր հղումը հաճախորդների համար՝\n{link}",
    "MY_INVITES_EMPTY": "Դեռ հրավերներ չեք ստեղծել։",
    "MY_INVITES_HEADER": "Ձեր հրավերները․",
    "MY_INVITES_ITEM_FMT": "`{code}` · {status} · {expires}",
    "MY_INVITES_STATUS_ACTIVE": "ակտիվ",
    "MY_INVITES_STATUS_USED": "օգտագործված",
    "MY_INVITES_STATUS_EXPIRED": "ժամկետանց",
    "NEW_INVITE_BTN": "➕ Հրավիրել վարպետ",
    "SETTINGS_BTN_MY_LINK": "🔗 Իմ հղումը",
    "SETTINGS_BTN_MY_INVITES": "📨 Իմ հրավերները",
    "SETTINGS_BTN_NEW_INVITE": "➕ Հրավիրել վարպետ",
    "SETTINGS_BTN_PROFILE": "👤 Իմ պրոֆիլը",
    "SETTINGS_BTN_ADMIN": "🛠 Ադմին",
    "PROFILE_MENU_TITLE": "Ի՞նչ փոխել։",
    "PROFILE_BTN_NAME": "✏️ Անուն",
    "PROFILE_BTN_SPECIALTY": "✏️ Մասնագիտություն",
    "PROFILE_BTN_SLUG": "✏️ Հասցե (slug)",
    "PROFILE_ASK_NEW_NAME": "Մուտքագրեք նոր անունը․",
    "PROFILE_ASK_NEW_SPECIALTY": "Մուտքագրեք մասնագիտությունը․",
    "PROFILE_ASK_NEW_SLUG": "Մուտքագրեք նոր հասցեն (3–32 սիմվոլ)․",
    "PROFILE_UPDATED": "Պատրաստ է ✅",
    "CLIENT_CATALOG_HEADER": "Ընտրեք վարպետ․",
    "CLIENT_CATALOG_EMPTY": "Վարպետներ դեռ գրանցված չեն։",
    "CLIENT_CATALOG_CARD_FMT": "👤 {name} — {specialty}",
    "CLIENT_CATALOG_PICK_BTN": "📅 Գրանցվել",
    "CLIENT_MASTER_NOT_FOUND": "Վարպետ չի գտնվել։",
    "CLIENT_MASTER_CARD_FMT": "👤 {name}\n{specialty}",
    "CLIENT_BOOK_HERE_BTN": "📅 Գրանցվել",
    "MASTER_BLOCKED_BANNER": "⛔ Ձեր կաբինետը ժամանակավոր արգելափակված է ադմինիստրատորի կողմից։",
    "CLIENT_APPT_REJECTED_BLOCK": "Ցավոք, վարպետն այս պահին հասանելի չէ։ Ձեր դիմումը չեղարկված է։",
    "ADMIN_MENU_TITLE": "Ադմին մենյու․",
    "ADMIN_MENU_MASTERS": "👥 Վարպետներ",
    "ADMIN_MENU_STATS": "📊 Վիճակագրություն",
    "ADMIN_MENU_INVITES": "📨 Հրավերներ",
    "ADMIN_MENU_MODERATION": "🛠 Մոդերացիա",
    "ADMIN_MENU_BACK": "⬅️ Գլխավոր մենյու",
    "ADMIN_MASTERS_HEADER": "Բոլոր վարպետները․",
    "ADMIN_MASTERS_EMPTY": "Վարպետներ դեռ չկան։",
    "ADMIN_MASTER_ITEM_FMT": "`{slug}` · {name} · {status}",
    "ADMIN_MASTER_STATUS_ACTIVE": "ակտիվ",
    "ADMIN_MASTER_STATUS_BLOCKED": "արգելափակված",
    "ADMIN_BLOCK_BTN": "🚫 Արգելափակել",
    "ADMIN_UNBLOCK_BTN": "✅ Վերականգնել",
    "ADMIN_BLOCK_DONE_FMT": "Վարպետը {slug} արգելափակված է։ Չեղարկված pending՝ {n}։",
    "ADMIN_UNBLOCK_DONE_FMT": "Վարպետը {slug} վերականգնված է։",
    "ADMIN_STATS_FMT": (
        "📊 Վիճակագրություն\n\n"
        "Վարպետներ՝ {masters_active} ակտիվ / {masters_blocked} արգելափակված\n"
        "Հաճախորդներ (ունիկալ)՝ {clients}\n"
        "Գրանցումներ 7 օրում՝ {appt_7d}\n"
        "Գրանցումներ 30 օրում՝ {appt_30d}"
    ),
    "ADMIN_INVITES_HEADER": "Բոլոր հրավերները․",
    "ADMIN_INVITE_ITEM_FMT": "`{code}` · {status} · {creator_tg_id}-ի կողմից",
    "ADMIN_MASTER_NOT_FOUND": "Այս slug-ով վարպետ չի գտնվել։",
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/test_strings_epic9_keys.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/strings.py tests/test_strings_epic9_keys.py
git commit -m "feat(strings): RU+HY strings for Epic 9 multi-master"
```

---

### Task 9: Callback data — registration/admin/catalog

**Files:**
- Create: `src/callback_data/registration.py`
- Create: `src/callback_data/admin.py`
- Create: `src/callback_data/catalog.py`
- Test: `tests/test_callback_data_epic9.py` (NEW)

- [ ] **Step 1: Написать тесты**

```python
from __future__ import annotations

from uuid import uuid4

from src.callback_data.admin import AdminMasterCallback, BlockCallback
from src.callback_data.catalog import CatalogMasterCallback
from src.callback_data.registration import SlugConfirmCallback, SpecialtyHintCallback


def test_specialty_hint_pack_unpack() -> None:
    cb = SpecialtyHintCallback(hint="hair")
    packed = cb.pack()
    unpacked = SpecialtyHintCallback.unpack(packed)
    assert unpacked.hint == "hair"


def test_slug_confirm_pack_unpack() -> None:
    for action in ("use", "change"):
        cb = SlugConfirmCallback(action=action)
        unpacked = SlugConfirmCallback.unpack(cb.pack())
        assert unpacked.action == action


def test_admin_master_pack_unpack() -> None:
    mid = uuid4()
    cb = AdminMasterCallback(master_id=mid, action="view")
    u = AdminMasterCallback.unpack(cb.pack())
    assert u.master_id == mid and u.action == "view"


def test_block_callback() -> None:
    mid = uuid4()
    cb = BlockCallback(master_id=mid, block=True)
    u = BlockCallback.unpack(cb.pack())
    assert u.master_id == mid and u.block is True


def test_catalog_master_callback() -> None:
    mid = uuid4()
    cb = CatalogMasterCallback(master_id=mid)
    u = CatalogMasterCallback.unpack(cb.pack())
    assert u.master_id == mid
```

- [ ] **Step 2: Реализовать `src/callback_data/registration.py`**

```python
from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class SpecialtyHintCallback(CallbackData, prefix="sph"):
    hint: Literal["hair", "dentist", "nails", "cosmetologist", "custom"]


class SlugConfirmCallback(CallbackData, prefix="slc"):
    action: Literal["use", "change"]
```

- [ ] **Step 3: Реализовать `src/callback_data/admin.py`**

```python
from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class AdminMasterCallback(CallbackData, prefix="adm"):
    master_id: UUID
    action: Literal["view", "back"]


class BlockCallback(CallbackData, prefix="blk"):
    master_id: UUID
    block: bool
```

- [ ] **Step 4: Реализовать `src/callback_data/catalog.py`**

```python
from __future__ import annotations

from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class CatalogMasterCallback(CallbackData, prefix="cat"):
    master_id: UUID
```

- [ ] **Step 5: Run — expect PASS**

Run: `pytest tests/test_callback_data_epic9.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/callback_data/registration.py src/callback_data/admin.py \
  src/callback_data/catalog.py tests/test_callback_data_epic9.py
git commit -m "feat(cb): typed callback data for registration/admin/catalog"
```

---

### Task 10: FSM — расширить MasterRegister

**Files:**
- Modify: `src/fsm/master_register.py`

- [ ] **Step 1: Написать тест**

Файл `tests/test_fsm_master_register_epic9.py` (NEW):

```python
from __future__ import annotations

from aiogram.fsm.state import State

from src.fsm.master_register import MasterRegister


def test_new_states_exist() -> None:
    assert isinstance(MasterRegister.waiting_specialty, State)
    assert isinstance(MasterRegister.waiting_slug_confirm, State)
    assert isinstance(MasterRegister.waiting_custom_slug, State)
```

- [ ] **Step 2: Добавить состояния в `src/fsm/master_register.py`**

```python
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MasterRegister(StatesGroup):
    waiting_lang = State()
    waiting_name = State()
    waiting_phone = State()
    waiting_specialty = State()
    waiting_slug_confirm = State()
    waiting_custom_slug = State()
```

- [ ] **Step 3: Run — expect PASS**

Run: `pytest tests/test_fsm_master_register_epic9.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/fsm/master_register.py tests/test_fsm_master_register_epic9.py
git commit -m "feat(fsm): MasterRegister — add specialty/slug_confirm/custom_slug states"
```

---

### Task 11: UserMiddleware — убрать клиентский lookup

**Files:**
- Modify: `src/middlewares/user.py`
- Modify: `tests/test_middleware_user.py` (обновить существующие тесты)

- [ ] **Step 1: Обновить тесты**

Полностью переписать `tests/test_middleware_user.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import pytest
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master
from src.middlewares.user import UserMiddleware


@dataclass
class FakeUser:
    id: int


@dataclass
class FakeEvent:
    from_user: FakeUser


@pytest.mark.asyncio
async def test_resolves_existing_master(session: AsyncSession) -> None:
    master = Master(tg_id=100001, name="Анна", slug="anna-0001")
    session.add(master)
    await session.commit()

    middleware = UserMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    await middleware(
        handler,
        cast(TelegramObject, FakeEvent(from_user=FakeUser(id=100001))),
        {"session": session},
    )

    assert captured["master"] is not None
    assert captured["master"].tg_id == 100001


@pytest.mark.asyncio
async def test_master_not_shadowed_by_client_at_other_master(session: AsyncSession) -> None:
    """Regression: old code did session.scalar for client, which would crash on
    MultipleResultsFound. Even if it succeeded, we must not populate client data."""
    m1 = Master(tg_id=100001, name="A", slug="a-0001")
    m2 = Master(tg_id=100002, name="B", slug="b-0001")
    session.add_all([m1, m2])
    await session.flush()
    # Same tg_id 300001 is a client of BOTH masters
    session.add(Client(master_id=m1.id, name="X", phone="+111", tg_id=300001))
    session.add(Client(master_id=m2.id, name="X", phone="+222", tg_id=300001))
    await session.commit()

    middleware = UserMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    # Must not crash even though two clients rows exist.
    await middleware(
        handler,
        cast(TelegramObject, FakeEvent(from_user=FakeUser(id=300001))),
        {"session": session},
    )
    assert captured["master"] is None
    # Middleware no longer resolves `client` — handlers do it with master_id scope.
    assert "client" in captured  # key still present for compat
    assert captured["client"] is None


@pytest.mark.asyncio
async def test_unknown_user_has_nones(session: AsyncSession) -> None:
    middleware = UserMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    await middleware(
        handler,
        cast(TelegramObject, FakeEvent(from_user=FakeUser(id=999999))),
        {"session": session},
    )

    assert captured["master"] is None
    assert captured["client"] is None
```

- [ ] **Step 2: Обновить `src/middlewares/user.py`**

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master


class UserMiddleware(BaseMiddleware):
    """Resolve Master (if any) by Telegram user id and attach to handler data.

    Client resolution is intentionally NOT done here — in a multi-master bot one
    tg_id may be a client of multiple masters, so client lookup must be scoped
    by master_id and performed at the service layer.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["master"] = None
        data["client"] = None  # kept for handler compatibility

        inner = event.event if isinstance(event, Update) else event
        tg_user = getattr(inner, "from_user", None)
        if tg_user is None:
            return await handler(event, data)

        session: AsyncSession = data["session"]

        master = await session.scalar(
            select(Master).where(Master.tg_id == tg_user.id)
        )
        if master is not None:
            data["master"] = master

        return await handler(event, data)
```

- [ ] **Step 3: Run — expect PASS**

Run: `pytest tests/test_middleware_user.py -v`
Expected: PASS (включая новый regression-тест).

- [ ] **Step 4: Убедиться что старые хендлеры, зависящие от `client` middleware-значения, переживают**

Run: `grep -rn '"client"\]\|data\["client"\]\|kwargs.*client' src/handlers/`
Это список мест, где хендлеры читают client из data. Проверить, что везде handler работает с `client: Client | None = None` и не падает на None.

Если где-то handler падает — нужно в следующем таске фиксить client-lookup на уровне сервиса. Отметить как known gap, НЕ блокирующий.

- [ ] **Step 5: Полный pytest**

Run: `pytest -q`
Expected: всё зелёное. Если что-то упало из-за изменения middleware — зафиксить в том же коммите.

- [ ] **Step 6: Commit**

```bash
git add src/middlewares/user.py tests/test_middleware_user.py
git commit -m "fix(middleware): UserMiddleware drops client lookup (multi-master safe)"
```

---

### Task 12: AdminMiddleware — проставляет data["is_admin"]

**Files:**
- Create: `src/middlewares/admin.py`
- Modify: `src/main.py` (зарегистрировать после UserMiddleware)
- Test: `tests/test_middleware_admin.py` (NEW)

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import patch

import pytest
from aiogram.types import TelegramObject

from src.middlewares.admin import AdminMiddleware


@dataclass
class FakeUser:
    id: int


@dataclass
class FakeEvent:
    from_user: FakeUser | None


@pytest.mark.asyncio
async def test_admin_flag_true_for_admin_tg_id() -> None:
    middleware = AdminMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    with patch("src.middlewares.admin.settings") as mocked:
        mocked.admin_tg_ids = [100]
        await middleware(
            handler,
            cast(TelegramObject, FakeEvent(from_user=FakeUser(id=100))),
            {},
        )
    assert captured["is_admin"] is True


@pytest.mark.asyncio
async def test_admin_flag_false_for_non_admin() -> None:
    middleware = AdminMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    with patch("src.middlewares.admin.settings") as mocked:
        mocked.admin_tg_ids = [100]
        await middleware(
            handler,
            cast(TelegramObject, FakeEvent(from_user=FakeUser(id=200))),
            {},
        )
    assert captured["is_admin"] is False


@pytest.mark.asyncio
async def test_admin_flag_false_without_user() -> None:
    middleware = AdminMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    with patch("src.middlewares.admin.settings") as mocked:
        mocked.admin_tg_ids = [100]
        await middleware(
            handler,
            cast(TelegramObject, FakeEvent(from_user=None)),
            {},
        )
    assert captured["is_admin"] is False
```

- [ ] **Step 2: Реализовать `src/middlewares/admin.py`**

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from src.config import settings


class AdminMiddleware(BaseMiddleware):
    """Populate ``data['is_admin']`` based on ADMIN_TG_IDS env."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["is_admin"] = False

        inner = event.event if isinstance(event, Update) else event
        tg_user = getattr(inner, "from_user", None)
        if tg_user is not None and tg_user.id in settings.admin_tg_ids:
            data["is_admin"] = True

        return await handler(event, data)
```

- [ ] **Step 3: Зарегистрировать в `src/main.py`**

В `build_dispatcher`, после `dp.update.middleware(UserMiddleware())`:

```python
    dp.update.middleware(AdminMiddleware())
```

Также добавить импорт: `from src.middlewares.admin import AdminMiddleware`.

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/test_middleware_admin.py -v && pytest -q`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add src/middlewares/admin.py src/main.py tests/test_middleware_admin.py
git commit -m "feat(middleware): AdminMiddleware marks is_admin from ADMIN_TG_IDS"
```

---

### Task 13: MasterRegistrationService — транзакционная регистрация

**Files:**
- Create: `src/services/master_registration.py`
- Test: `tests/test_services_master_registration.py` (NEW)

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master
from src.exceptions import InviteAlreadyUsed, InviteExpired, InviteNotFound, SlugTaken
from src.services.master_registration import MasterRegistrationService


@pytest.mark.asyncio
async def test_register_happy_path(session: AsyncSession) -> None:
    inv = Invite(
        code="REG-0001", created_by_tg_id=1,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(inv)
    await session.commit()

    svc = MasterRegistrationService(session)
    master = await svc.register(
        tg_id=500001,
        name="Арам",
        specialty="Стоматолог",
        slug="aram-test",
        lang="ru",
        invite_code="REG-0001",
    )
    await session.commit()
    assert master.tg_id == 500001 and master.slug == "aram-test"
    assert master.specialty_text == "Стоматолог"
    await session.refresh(inv)
    assert inv.used_by_tg_id == 500001


@pytest.mark.asyncio
async def test_register_rejects_invalid_invite(session: AsyncSession) -> None:
    svc = MasterRegistrationService(session)
    with pytest.raises(InviteNotFound):
        await svc.register(
            tg_id=500002, name="X", specialty="",
            slug="x-xxxx", lang="ru", invite_code="MISSING",
        )


@pytest.mark.asyncio
async def test_register_rejects_taken_slug(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="taken-0001")
    inv = Invite(
        code="REG-TK01", created_by_tg_id=1,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add_all([m, inv])
    await session.commit()

    svc = MasterRegistrationService(session)
    with pytest.raises(SlugTaken):
        await svc.register(
            tg_id=999, name="New", specialty="",
            slug="taken-0001", lang="ru", invite_code="REG-TK01",
        )
```

- [ ] **Step 2: Реализовать `src/services/master_registration.py`**

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.exceptions import SlugTaken
from src.repositories.masters import MasterRepository
from src.services.invite import InviteService


class MasterRegistrationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._masters = MasterRepository(session)
        self._invites = InviteService(session)

    async def register(
        self,
        *,
        tg_id: int,
        name: str,
        specialty: str,
        slug: str,
        lang: str,
        invite_code: str,
    ) -> Master:
        # Pre-check slug collision to raise a clean domain error
        existing = await self._session.scalar(
            select(Master).where(Master.slug == slug)
        )
        if existing is not None:
            raise SlugTaken(slug)

        master = Master(
            tg_id=tg_id, name=name, slug=slug,
            specialty_text=specialty, lang=lang,
        )
        self._session.add(master)
        try:
            await self._session.flush()
        except IntegrityError as e:
            raise SlugTaken(slug) from e

        # Redeem invite (validates expired/used/missing)
        await self._invites.redeem(
            code=invite_code, tg_id=tg_id, master_id=master.id
        )
        return master
```

- [ ] **Step 3: Run — expect PASS**

Run: `pytest tests/test_services_master_registration.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/services/master_registration.py tests/test_services_master_registration.py
git commit -m "feat(services): MasterRegistrationService — invite + slug atomic register"
```

---

### Task 14: ModerationService — block/unblock + bulk-reject

**Files:**
- Create: `src/services/moderation.py`
- Test: `tests/test_services_moderation.py` (NEW)

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.services.moderation import ModerationService


@pytest.mark.asyncio
async def test_block_sets_blocked_at_and_rejects_pending(
    session: AsyncSession,
) -> None:
    m = Master(tg_id=1, name="A", slug="a-0001")
    session.add(m)
    await session.flush()
    svc = Service(master_id=m.id, name="cut", duration_min=30)
    cli = Client(master_id=m.id, name="C", phone="+111", tg_id=999)
    session.add_all([svc, cli])
    await session.flush()
    now = datetime.now(timezone.utc)
    appt = Appointment(
        master_id=m.id, client_id=cli.id, service_id=svc.id,
        start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=2),
        status="pending", source="client_request",
    )
    session.add(appt)
    await session.commit()

    service = ModerationService(session)
    result = await service.block_master(m.id)
    await session.commit()

    await session.refresh(m)
    await session.refresh(appt)
    assert m.blocked_at is not None
    assert appt.status == "rejected"
    assert len(result.rejected) == 1
    assert result.rejected[0].client_tg_id == 999


@pytest.mark.asyncio
async def test_unblock_clears_blocked_at(session: AsyncSession) -> None:
    m = Master(
        tg_id=1, name="A", slug="a-0001",
        blocked_at=datetime.now(timezone.utc),
    )
    session.add(m)
    await session.commit()
    svc = ModerationService(session)
    await svc.unblock_master(m.id)
    await session.commit()
    await session.refresh(m)
    assert m.blocked_at is None
```

- [ ] **Step 2: Реализовать `src/services/moderation.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client
from src.repositories.appointments import AppointmentRepository
from src.repositories.masters import MasterRepository


@dataclass
class RejectedInfo:
    appointment_id: UUID
    client_tg_id: int | None


@dataclass
class BlockResult:
    rejected: list[RejectedInfo]


class ModerationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._masters = MasterRepository(session)
        self._appts = AppointmentRepository(session)

    async def block_master(self, master_id: UUID) -> BlockResult:
        await self._masters.set_blocked(master_id, blocked=True)
        rejected_appts = await self._appts.bulk_reject_pending_for_master(
            master_id, reason="master_blocked"
        )
        # Resolve client tg_ids for notifications
        out: list[RejectedInfo] = []
        for appt in rejected_appts:
            client = await self._session.scalar(
                select(Client).where(Client.id == appt.client_id)
            )
            out.append(
                RejectedInfo(
                    appointment_id=appt.id,
                    client_tg_id=client.tg_id if client else None,
                )
            )
        return BlockResult(rejected=out)

    async def unblock_master(self, master_id: UUID) -> None:
        await self._masters.set_blocked(master_id, blocked=False)
```

- [ ] **Step 3: Run — expect PASS**

Run: `pytest tests/test_services_moderation.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/services/moderation.py tests/test_services_moderation.py
git commit -m "feat(services): ModerationService — block/unblock with bulk-reject"
```

---

### Task 15: Keyboards — registration, catalog, admin

**Files:**
- Create: `src/keyboards/registration.py`
- Create: `src/keyboards/catalog.py`
- Create: `src/keyboards/admin.py`
- Test: `tests/test_keyboards_epic9.py` (NEW)

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from uuid import uuid4

from src.db.models import Master
from src.keyboards.admin import admin_menu, masters_list_kb
from src.keyboards.catalog import catalog_kb
from src.keyboards.registration import slug_confirm_kb, specialty_hints_kb
from src.strings import get_bundle


def test_specialty_hints_has_5_buttons() -> None:
    kb = specialty_hints_kb()
    flat = [btn.text for row in kb.inline_keyboard for btn in row]
    assert len(flat) == 5
    ru = get_bundle("ru")
    assert ru.REGISTER_SPECIALTY_HINT_HAIR in flat
    assert ru.REGISTER_SPECIALTY_HINT_CUSTOM in flat


def test_slug_confirm_has_use_and_change() -> None:
    kb = slug_confirm_kb()
    flat = [btn.text for row in kb.inline_keyboard for btn in row]
    ru = get_bundle("ru")
    assert ru.REGISTER_SLUG_USE_BTN in flat
    assert ru.REGISTER_SLUG_CHANGE_BTN in flat


def test_admin_menu_structure() -> None:
    kb = admin_menu()
    texts = [btn.text for row in kb.keyboard for btn in row]
    ru = get_bundle("ru")
    assert ru.ADMIN_MENU_MASTERS in texts
    assert ru.ADMIN_MENU_STATS in texts
    assert ru.ADMIN_MENU_INVITES in texts
    assert ru.ADMIN_MENU_MODERATION in texts


def test_masters_list_kb_per_master_buttons() -> None:
    m1 = Master(tg_id=1, name="A", slug="a-0001")
    m2 = Master(tg_id=2, name="B", slug="b-0001")
    m1.id = uuid4()
    m2.id = uuid4()
    kb = masters_list_kb([m1, m2])
    # At least one button per master
    all_btns = [b for row in kb.inline_keyboard for b in row]
    assert len(all_btns) >= 2


def test_catalog_kb_has_button_per_master() -> None:
    m1 = Master(tg_id=1, name="A", slug="a-0001", specialty_text="Dentist")
    m1.id = uuid4()
    kb = catalog_kb([m1])
    assert len(kb.inline_keyboard) == 1


def test_catalog_kb_empty_returns_empty_keyboard() -> None:
    kb = catalog_kb([])
    assert kb.inline_keyboard == []
```

- [ ] **Step 2: Реализовать `src/keyboards/registration.py`**

```python
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.registration import SlugConfirmCallback, SpecialtyHintCallback
from src.strings import strings


def specialty_hints_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.REGISTER_SPECIALTY_HINT_HAIR,
                    callback_data=SpecialtyHintCallback(hint="hair").pack(),
                ),
                InlineKeyboardButton(
                    text=strings.REGISTER_SPECIALTY_HINT_DENTIST,
                    callback_data=SpecialtyHintCallback(hint="dentist").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=strings.REGISTER_SPECIALTY_HINT_NAILS,
                    callback_data=SpecialtyHintCallback(hint="nails").pack(),
                ),
                InlineKeyboardButton(
                    text=strings.REGISTER_SPECIALTY_HINT_COSMETOLOGIST,
                    callback_data=SpecialtyHintCallback(hint="cosmetologist").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=strings.REGISTER_SPECIALTY_HINT_CUSTOM,
                    callback_data=SpecialtyHintCallback(hint="custom").pack(),
                ),
            ],
        ]
    )


def slug_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.REGISTER_SLUG_USE_BTN,
                    callback_data=SlugConfirmCallback(action="use").pack(),
                ),
                InlineKeyboardButton(
                    text=strings.REGISTER_SLUG_CHANGE_BTN,
                    callback_data=SlugConfirmCallback(action="change").pack(),
                ),
            ]
        ]
    )
```

- [ ] **Step 3: Реализовать `src/keyboards/catalog.py`**

```python
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.catalog import CatalogMasterCallback
from src.db.models import Master
from src.strings import strings


def catalog_kb(masters: list[Master]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for m in masters:
        label = strings.CLIENT_CATALOG_CARD_FMT.format(
            name=m.name,
            specialty=m.specialty_text or "—",
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=CatalogMasterCallback(master_id=m.id).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 4: Реализовать `src/keyboards/admin.py`**

```python
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from src.callback_data.admin import AdminMasterCallback, BlockCallback
from src.db.models import Master
from src.strings import strings


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=strings.ADMIN_MENU_MASTERS),
                KeyboardButton(text=strings.ADMIN_MENU_STATS),
            ],
            [
                KeyboardButton(text=strings.ADMIN_MENU_INVITES),
                KeyboardButton(text=strings.ADMIN_MENU_MODERATION),
            ],
            [KeyboardButton(text=strings.ADMIN_MENU_BACK)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def masters_list_kb(masters: list[Master]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for m in masters:
        is_blocked = m.blocked_at is not None
        status = (
            strings.ADMIN_MASTER_STATUS_BLOCKED
            if is_blocked
            else strings.ADMIN_MASTER_STATUS_ACTIVE
        )
        label = f"{m.slug} · {m.name} · {status}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=AdminMasterCallback(
                        master_id=m.id, action="view"
                    ).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def block_toggle_kb(master: Master) -> InlineKeyboardMarkup:
    is_blocked = master.blocked_at is not None
    btn_text = (
        strings.ADMIN_UNBLOCK_BTN if is_blocked else strings.ADMIN_BLOCK_BTN
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=BlockCallback(
                        master_id=master.id, block=not is_blocked
                    ).pack(),
                )
            ]
        ]
    )
```

- [ ] **Step 5: Run — expect PASS**

Run: `pytest tests/test_keyboards_epic9.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/keyboards/registration.py src/keyboards/catalog.py \
  src/keyboards/admin.py tests/test_keyboards_epic9.py
git commit -m "feat(keyboards): registration hints, catalog, admin menu"
```

---

### Task 16: main_menu — добавить "🔗 Моя ссылка"

**Files:**
- Modify: `src/keyboards/common.py:14-35`
- Modify: `tests/test_keyboards_main_menu.py`

- [ ] **Step 1: Обновить тест**

Добавить в `tests/test_keyboards_main_menu.py`:

```python
def test_main_menu_contains_my_link_button_in_ru() -> None:
    ru = get_bundle("ru")
    texts = _all_button_texts()
    assert ru.MAIN_MENU_MY_LINK in texts
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/test_keyboards_main_menu.py::test_main_menu_contains_my_link_button_in_ru -v`
Expected: FAIL (кнопки ещё нет).

- [ ] **Step 3: Обновить `src/keyboards/common.py` — `main_menu()`**

```python
def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=strings.MAIN_MENU_TODAY),
                KeyboardButton(text=strings.MAIN_MENU_TOMORROW),
            ],
            [
                KeyboardButton(text=strings.MAIN_MENU_WEEK),
                KeyboardButton(text=strings.MAIN_MENU_CALENDAR),
            ],
            [
                KeyboardButton(text=strings.MAIN_MENU_ADD),
                KeyboardButton(text=strings.MAIN_MENU_CLIENT),
            ],
            [
                KeyboardButton(text=strings.MAIN_MENU_MY_LINK),
                KeyboardButton(text=strings.MAIN_MENU_SETTINGS),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/test_keyboards_main_menu.py -v`
Expected: PASS (и старые тесты тоже).

- [ ] **Step 5: Commit**

```bash
git add src/keyboards/common.py tests/test_keyboards_main_menu.py
git commit -m "feat(ui): add '🔗 Моя ссылка' button to master main_menu"
```

---

### Task 17: my_link — кнопка, handler, button-dispatch test

**Files:**
- Create: `src/handlers/master/my_link.py`
- Modify: `src/handlers/master/menu.py` (добавить dispatch)
- Modify: `src/handlers/master/__init__.py` (include_router)
- Modify: `tests/test_handlers_master_menu_dispatch.py` (добавить my_link test)
- Test: `tests/test_handlers_master_my_link.py` (NEW)

- [ ] **Step 1: Тест handler'а cmd_mylink**

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.handlers.master.my_link import cmd_mylink


@pytest.mark.asyncio
async def test_cmd_mylink_sends_link_with_slug() -> None:
    message = AsyncMock()
    master = AsyncMock()
    master.slug = "anna-7f3c"
    with patch("src.handlers.master.my_link.strings") as mocked:
        mocked.MY_LINK_MSG_FMT = "link: {link}"
        await cmd_mylink(message=message, master=master)
    message.answer.assert_awaited_once()
    args = message.answer.await_args
    assert "anna-7f3c" in args[0][0]
```

- [ ] **Step 2: Реализовать `src/handlers/master/my_link.py`**

```python
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.db.models import Master
from src.strings import strings

router = Router(name="master_my_link")


async def cmd_mylink(*, message: Message, master: Master) -> None:
    link = f"https://t.me/grancvi_bot?start=master_{master.slug}"
    await message.answer(strings.MY_LINK_MSG_FMT.format(link=link))


@router.message(Command("mylink"))
async def handle_mylink_cmd(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await cmd_mylink(message=message, master=master)
```

- [ ] **Step 3: Подключить router в `src/handlers/master/__init__.py`**

Добавить импорт и include_router перед client_page_router:

```python
from src.handlers.master.my_link import router as my_link_router
# ...
router.include_router(my_link_router)
```

- [ ] **Step 4: Добавить button-dispatch в menu.py**

В `src/handlers/master/menu.py` добавить импорт:

```python
from src.handlers.master.my_link import cmd_mylink
```

И обработчик:

```python
@router.message(F.text.in_({_RU_MENU.MAIN_MENU_MY_LINK, _HY_MENU.MAIN_MENU_MY_LINK}))
async def handle_my_link(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await cmd_mylink(message=message, master=master)
```

- [ ] **Step 5: Button-dispatch test**

В `tests/test_handlers_master_menu_dispatch.py`:

```python
@pytest.mark.asyncio
async def test_my_link_button_dispatches_to_cmd_mylink() -> None:
    message = AsyncMock()
    master = AsyncMock(id=uuid4())

    with patch.object(menu_mod, "cmd_mylink", new=AsyncMock()) as mocked:
        await menu_mod.handle_my_link(message=message, master=master)

    mocked.assert_awaited_once_with(message=message, master=master)


@pytest.mark.asyncio
async def test_my_link_noop_for_non_master() -> None:
    message = AsyncMock()
    with patch.object(menu_mod, "cmd_mylink", new=AsyncMock()) as mocked:
        await menu_mod.handle_my_link(message=message, master=None)
    mocked.assert_not_awaited()
```

- [ ] **Step 6: Run — expect PASS**

Run: `pytest tests/test_handlers_master_my_link.py tests/test_handlers_master_menu_dispatch.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/handlers/master/my_link.py src/handlers/master/menu.py \
  src/handlers/master/__init__.py tests/test_handlers_master_my_link.py \
  tests/test_handlers_master_menu_dispatch.py
git commit -m "feat(master): '🔗 Моя ссылка' button + /mylink command"
```

---

### Task 18: new_invite — кнопка и handler

**Files:**
- Create: `src/handlers/master/new_invite.py`
- Modify: `src/handlers/master/__init__.py`
- Test: `tests/test_handlers_master_new_invite.py` (NEW)

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master
from src.handlers.master.new_invite import cmd_new_invite


@pytest.mark.asyncio
async def test_new_invite_creates_invite_and_sends_link(
    session: AsyncSession,
) -> None:
    master = Master(tg_id=101, name="A", slug="a-0001")
    session.add(master)
    await session.commit()

    message = AsyncMock()
    message.from_user = AsyncMock(id=101)

    with patch("src.handlers.master.new_invite.strings") as mocked_strings:
        mocked_strings.INVITE_CREATED_FMT = (
            "code: {code} link: {link} expires: {expires}"
        )
        await cmd_new_invite(message=message, session=session, master=master)
        await session.commit()

    # An invite row was created
    from sqlalchemy import select
    invite = await session.scalar(
        select(Invite).where(Invite.created_by_tg_id == 101)
    )
    assert invite is not None
    message.answer.assert_awaited_once()
    sent = message.answer.await_args[0][0]
    assert invite.code in sent
    assert f"invite_{invite.code}" in sent
```

- [ ] **Step 2: Реализовать `src/handlers/master/new_invite.py`**

```python
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.services.invite import InviteService
from src.strings import strings

router = Router(name="master_new_invite")


async def cmd_new_invite(
    *,
    message: Message,
    session: AsyncSession,
    master: Master,
) -> None:
    svc = InviteService(session)
    invite = await svc.create_invite(actor_tg_id=master.tg_id)
    link = f"https://t.me/grancvi_bot?start=invite_{invite.code}"
    text = strings.INVITE_CREATED_FMT.format(
        code=invite.code,
        link=link,
        expires=invite.expires_at.strftime("%Y-%m-%d %H:%M UTC"),
    )
    await message.answer(text)


@router.message(Command("new_invite"))
async def handle_new_invite_cmd(
    message: Message,
    session: AsyncSession,
    master: Master | None,
    is_admin: bool = False,
) -> None:
    # Master OR admin can create invites
    if master is None and not is_admin:
        return
    actor_tg = master.tg_id if master else (
        message.from_user.id if message.from_user else 0
    )
    if master is None:
        # Admin without master profile: use admin tg_id as creator
        svc = InviteService(session)
        invite = await svc.create_invite(actor_tg_id=actor_tg)
        link = f"https://t.me/grancvi_bot?start=invite_{invite.code}"
        await message.answer(
            strings.INVITE_CREATED_FMT.format(
                code=invite.code, link=link,
                expires=invite.expires_at.strftime("%Y-%m-%d %H:%M UTC"),
            )
        )
        return
    await cmd_new_invite(message=message, session=session, master=master)
```

- [ ] **Step 3: Подключить router**

В `src/handlers/master/__init__.py` добавить импорт+include:

```python
from src.handlers.master.new_invite import router as new_invite_router
# ...
router.include_router(new_invite_router)
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/test_handlers_master_new_invite.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/handlers/master/new_invite.py src/handlers/master/__init__.py \
  tests/test_handlers_master_new_invite.py
git commit -m "feat(master): /new_invite command for masters+admins"
```

---

### Task 19: my_invites — список инвайтов мастера

**Files:**
- Create: `src/handlers/master/my_invites.py`
- Modify: `src/handlers/master/__init__.py`
- Test: `tests/test_handlers_master_my_invites.py` (NEW)

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master
from src.handlers.master.my_invites import cmd_myinvites


@pytest.mark.asyncio
async def test_empty_sends_empty_msg(session: AsyncSession) -> None:
    master = Master(tg_id=1, name="A", slug="a-0001")
    session.add(master)
    await session.commit()
    message = AsyncMock()
    await cmd_myinvites(message=message, session=session, master=master)
    message.answer.assert_awaited_once()
    text = message.answer.await_args[0][0]
    from src.strings import get_bundle
    ru = get_bundle("ru")
    assert ru.MY_INVITES_EMPTY in text


@pytest.mark.asyncio
async def test_lists_invites_with_status(session: AsyncSession) -> None:
    master = Master(tg_id=1, name="A", slug="a-0001")
    session.add(master)
    await session.flush()
    now = datetime.now(timezone.utc)
    session.add(
        Invite(code="ACT-0001", created_by_tg_id=1,
               expires_at=now + timedelta(days=1))
    )
    session.add(
        Invite(code="EXP-0001", created_by_tg_id=1,
               expires_at=now - timedelta(days=1))
    )
    session.add(
        Invite(
            code="USD-0001", created_by_tg_id=1,
            expires_at=now + timedelta(days=1),
            used_by_tg_id=555, used_at=now, used_for_master_id=master.id,
        )
    )
    await session.commit()

    message = AsyncMock()
    await cmd_myinvites(message=message, session=session, master=master)
    text = message.answer.await_args[0][0]
    assert "ACT-0001" in text
    assert "EXP-0001" in text
    assert "USD-0001" in text
```

- [ ] **Step 2: Реализовать `src/handlers/master/my_invites.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master
from src.repositories.invites import InviteRepository
from src.strings import strings

router = Router(name="master_my_invites")


def _format_status(invite: Invite) -> str:
    if invite.used_at is not None:
        return strings.MY_INVITES_STATUS_USED
    if invite.expires_at <= datetime.now(timezone.utc):
        return strings.MY_INVITES_STATUS_EXPIRED
    return strings.MY_INVITES_STATUS_ACTIVE


async def cmd_myinvites(
    *,
    message: Message,
    session: AsyncSession,
    master: Master,
) -> None:
    repo = InviteRepository(session)
    invites = await repo.list_by_creator(master.tg_id)
    if not invites:
        await message.answer(strings.MY_INVITES_EMPTY)
        return
    lines = [strings.MY_INVITES_HEADER]
    for inv in invites:
        lines.append(
            strings.MY_INVITES_ITEM_FMT.format(
                code=inv.code,
                status=_format_status(inv),
                expires=inv.expires_at.strftime("%Y-%m-%d"),
            )
        )
    await message.answer("\n".join(lines))


@router.message(Command("myinvites"))
async def handle_myinvites_cmd(
    message: Message,
    session: AsyncSession,
    master: Master | None,
) -> None:
    if master is None:
        return
    await cmd_myinvites(message=message, session=session, master=master)
```

- [ ] **Step 3: Подключить router в `src/handlers/master/__init__.py`**

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/test_handlers_master_my_invites.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/handlers/master/my_invites.py src/handlers/master/__init__.py \
  tests/test_handlers_master_my_invites.py
git commit -m "feat(master): /myinvites lists invites with active/used/expired status"
```

---

### Task 20: Settings menu — добавить Profile / My invites / New invite

**Files:**
- Modify: `src/keyboards/settings.py`
- Modify: `src/handlers/master/settings.py`
- Test: `tests/test_keyboards_settings_epic9.py` (NEW)

- [ ] **Step 1: Тест keyboards**

```python
from __future__ import annotations

from src.keyboards.settings import settings_menu
from src.strings import get_bundle


def _all_texts() -> list[str]:
    kb = settings_menu()
    return [b.text for row in kb.inline_keyboard for b in row]


def test_settings_has_profile_button() -> None:
    ru = get_bundle("ru")
    assert ru.SETTINGS_BTN_PROFILE in _all_texts()


def test_settings_has_my_invites_button() -> None:
    ru = get_bundle("ru")
    assert ru.SETTINGS_BTN_MY_INVITES in _all_texts()


def test_settings_has_new_invite_button() -> None:
    ru = get_bundle("ru")
    assert ru.SETTINGS_BTN_NEW_INVITE in _all_texts()
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Обновить `src/keyboards/settings.py`**

В `SettingsCallback` добавить новые секции. Если там `section: Literal[...]`, расширить до `Literal["services", "hours", "breaks", "language", "profile", "my_invites", "new_invite"]`.

Проверь `src/callback_data/settings.py`:

Run: `cat src/callback_data/settings.py`

Если `Literal` — обнови там. Потом обнови `settings_menu()`:

```python
def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_PROFILE,
                    callback_data=SettingsCallback(section="profile").pack(),
                )
            ],
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
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_LANGUAGE,
                    callback_data=SettingsCallback(section="language").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_MY_INVITES,
                    callback_data=SettingsCallback(section="my_invites").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_NEW_INVITE,
                    callback_data=SettingsCallback(section="new_invite").pack(),
                )
            ],
        ]
    )
```

- [ ] **Step 4: Добавить callback-обработчики в `src/handlers/master/settings.py`**

Добавить в существующий settings-router:

```python
from src.handlers.master.my_invites import cmd_myinvites
from src.handlers.master.new_invite import cmd_new_invite
from src.handlers.master.profile import open_profile_menu  # from Task 21


@router.callback_query(SettingsCallback.filter(F.section == "my_invites"))
async def on_my_invites(
    cb: CallbackQuery,
    session: AsyncSession,
    master: Master | None,
) -> None:
    if master is None or cb.message is None:
        await cb.answer()
        return
    await cmd_myinvites(message=cb.message, session=session, master=master)
    await cb.answer()


@router.callback_query(SettingsCallback.filter(F.section == "new_invite"))
async def on_new_invite(
    cb: CallbackQuery,
    session: AsyncSession,
    master: Master | None,
) -> None:
    if master is None or cb.message is None:
        await cb.answer()
        return
    await cmd_new_invite(message=cb.message, session=session, master=master)
    await cb.answer()


@router.callback_query(SettingsCallback.filter(F.section == "profile"))
async def on_profile(
    cb: CallbackQuery,
    master: Master | None,
    state: FSMContext,
) -> None:
    if master is None or cb.message is None:
        await cb.answer()
        return
    await open_profile_menu(message=cb.message, state=state, master=master)
    await cb.answer()
```

- [ ] **Step 5: Run**

Run: `pytest tests/test_keyboards_settings_epic9.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/keyboards/settings.py src/handlers/master/settings.py \
  src/callback_data/settings.py tests/test_keyboards_settings_epic9.py
git commit -m "feat(ui): settings menu — profile, my_invites, new_invite entries"
```

---

### Task 21: Profile editor

**Files:**
- Create: `src/handlers/master/profile.py`
- Create: `src/fsm/profile.py`
- Create: `src/callback_data/profile.py`
- Modify: `src/handlers/master/__init__.py`
- Test: `tests/test_handlers_master_profile.py` (NEW)

- [ ] **Step 1: FSM для профиля**

`src/fsm/profile.py`:

```python
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ProfileEdit(StatesGroup):
    menu = State()
    waiting_name = State()
    waiting_specialty = State()
    waiting_slug = State()
```

- [ ] **Step 2: CallbackData**

`src/callback_data/profile.py`:

```python
from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class ProfileFieldCallback(CallbackData, prefix="pf"):
    field: Literal["name", "specialty", "slug"]
```

- [ ] **Step 3: Тест**

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.handlers.master.profile import cmd_profile_save_slug


@pytest.mark.asyncio
async def test_profile_save_slug_rejects_invalid() -> None:
    message = AsyncMock()
    message.text = "UPPER"
    state = AsyncMock()
    master = AsyncMock(id=uuid4())
    session = AsyncMock()
    await cmd_profile_save_slug(
        message=message, state=state, session=session, master=master
    )
    message.answer.assert_awaited()
    # No commit since invalid
    session.commit.assert_not_awaited()
```

- [ ] **Step 4: Реализовать `src/handlers/master/profile.py`**

```python
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.profile import ProfileFieldCallback
from src.db.models import Master
from src.exceptions import InvalidSlug, ReservedSlug, SlugTaken
from src.fsm.profile import ProfileEdit
from src.repositories.masters import MasterRepository
from src.services.slug import SlugService
from src.strings import strings

router = Router(name="master_profile")


def profile_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_BTN_NAME,
                    callback_data=ProfileFieldCallback(field="name").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_BTN_SPECIALTY,
                    callback_data=ProfileFieldCallback(field="specialty").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_BTN_SLUG,
                    callback_data=ProfileFieldCallback(field="slug").pack(),
                )
            ],
        ]
    )


async def open_profile_menu(
    *, message: Message, state: FSMContext, master: Master
) -> None:
    await state.set_state(ProfileEdit.menu)
    await message.answer(strings.PROFILE_MENU_TITLE, reply_markup=profile_menu_kb())


@router.callback_query(ProfileFieldCallback.filter(F.field == "name"))
async def pick_name(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileEdit.waiting_name)
    if cb.message is not None:
        await cb.message.answer(strings.PROFILE_ASK_NEW_NAME)
    await cb.answer()


@router.callback_query(ProfileFieldCallback.filter(F.field == "specialty"))
async def pick_specialty(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileEdit.waiting_specialty)
    if cb.message is not None:
        await cb.message.answer(strings.PROFILE_ASK_NEW_SPECIALTY)
    await cb.answer()


@router.callback_query(ProfileFieldCallback.filter(F.field == "slug"))
async def pick_slug(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileEdit.waiting_slug)
    if cb.message is not None:
        await cb.message.answer(strings.PROFILE_ASK_NEW_SLUG)
    await cb.answer()


@router.message(ProfileEdit.waiting_name)
async def cmd_profile_save_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(strings.PROFILE_ASK_NEW_NAME)
        return
    await MasterRepository(session).update_name(master.id, name)
    await session.commit()
    await state.clear()
    await message.answer(strings.PROFILE_UPDATED)


@router.message(ProfileEdit.waiting_specialty)
async def cmd_profile_save_specialty(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    specialty = (message.text or "").strip()
    if not specialty:
        await message.answer(strings.PROFILE_ASK_NEW_SPECIALTY)
        return
    await MasterRepository(session).update_specialty(master.id, specialty)
    await session.commit()
    await state.clear()
    await message.answer(strings.PROFILE_UPDATED)


@router.message(ProfileEdit.waiting_slug)
async def cmd_profile_save_slug(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
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

    repo = MasterRepository(session)
    existing = await repo.by_slug(slug)
    if existing is not None and existing.id != master.id:
        await message.answer(strings.REGISTER_SLUG_TAKEN)
        return

    try:
        await repo.update_slug(master.id, slug)
        await session.commit()
    except SlugTaken:
        await message.answer(strings.REGISTER_SLUG_TAKEN)
        return

    await state.clear()
    await message.answer(strings.PROFILE_UPDATED)
```

- [ ] **Step 5: Подключить router**

- [ ] **Step 6: Run — expect PASS**

Run: `pytest tests/test_handlers_master_profile.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/handlers/master/profile.py src/fsm/profile.py \
  src/callback_data/profile.py src/handlers/master/__init__.py \
  tests/test_handlers_master_profile.py
git commit -m "feat(master): profile editor — edit name, specialty, slug"
```

---

### Task 22: Master registration — инвайт deep-link + FSM

**Files:**
- Modify: `src/handlers/master/start.py` — добавить /start invite_<code> branch
- Create: `src/handlers/master/registration.py` — новые FSM steps
- Modify: `src/handlers/master/__init__.py`
- Test: `tests/test_handlers_master_registration.py` (NEW)

- [ ] **Step 1: Тест deep-link parse**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite
from src.fsm.master_register import MasterRegister
from src.handlers.master.start import handle_start


@pytest.mark.asyncio
async def test_start_with_valid_invite_starts_registration(
    session: AsyncSession,
) -> None:
    invite = Invite(
        code="AAAA-BBBB", created_by_tg_id=1,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(invite)
    await session.commit()

    message = AsyncMock()
    message.text = "/start invite_AAAA-BBBB"
    message.from_user = AsyncMock(id=999)
    state = AsyncMock()

    await handle_start(
        message=message, master=None, state=state, session=session
    )
    # Sets state to waiting_lang (first step is still lang pick)
    state.set_state.assert_any_call(MasterRegister.waiting_lang)
    # Stores invite_code in FSM data
    state.update_data.assert_any_call(invite_code="AAAA-BBBB")


@pytest.mark.asyncio
async def test_start_with_used_invite_shows_error(session: AsyncSession) -> None:
    from src.db.models import Master
    m = Master(tg_id=1, name="A", slug="a-0001")
    session.add(m)
    await session.flush()
    invite = Invite(
        code="USED-CODE", created_by_tg_id=1,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        used_by_tg_id=1, used_at=datetime.now(timezone.utc),
        used_for_master_id=m.id,
    )
    session.add(invite)
    await session.commit()

    message = AsyncMock()
    message.text = "/start invite_USED-CODE"
    message.from_user = AsyncMock(id=999)
    state = AsyncMock()

    await handle_start(
        message=message, master=None, state=state, session=session
    )
    message.answer.assert_awaited()
    sent = message.answer.await_args[0][0]
    from src.strings import get_bundle
    ru = get_bundle("ru")
    assert ru.INVITE_ALREADY_USED in sent
```

- [ ] **Step 2: Модифицировать `src/handlers/master/start.py`**

Обновить `handle_start`, чтобы парсить payload:

```python
from aiogram.filters import CommandObject, CommandStart

@router.message(CommandStart(deep_link=True), _InviteDeepLink())
async def handle_start_invite(
    message: Message,
    command: CommandObject,
    master: Master | None,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    # payload form: invite_XXXX-XXXX
    payload = command.args or ""
    if not payload.startswith("invite_"):
        return
    code = payload[len("invite_"):]

    if master is not None:
        await message.answer(strings.INVITE_ALREADY_MASTER)
        return

    repo = InviteRepository(session)
    invite = await repo.by_code(code)
    if invite is None:
        await message.answer(strings.INVITE_NOT_FOUND)
        return
    if invite.used_at is not None:
        await message.answer(strings.INVITE_ALREADY_USED)
        return
    if invite.expires_at <= datetime.now(timezone.utc):
        await message.answer(strings.INVITE_EXPIRED)
        return

    await state.clear()
    await state.update_data(invite_code=code)
    await state.set_state(MasterRegister.waiting_lang)
    await message.answer(strings.LANG_PICK_PROMPT, reply_markup=lang_picker())
```

И убрать `_IsMasterOrAdmin()` фильтр: теперь regular `handle_start` срабатывает только для master в сессии. Без admin-fallback — admin без профиля получит client-старт с каталогом (Task 25).

**Но:** admin без мастер-профиля должен получить `admin_menu()` (см. спеку §6.2). Это обработаем в admin-роутере (Task 27).

Итоговый `handle_start` для случая «master есть, payload нет»:

```python
@router.message(CommandStart())
async def handle_start(
    message: Message,
    master: Master | None,
    state: FSMContext,
) -> None:
    if master is None:
        return  # client router picks up
    await state.clear()
    await message.answer(strings.START_WELCOME_BACK, reply_markup=main_menu())
```

- [ ] **Step 3: Реализовать registration FSM steps**

`src/handlers/master/registration.py`:

```python
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.registration import SlugConfirmCallback, SpecialtyHintCallback
from src.exceptions import InvalidSlug, ReservedSlug, SlugTaken
from src.fsm.master_register import MasterRegister
from src.keyboards.common import main_menu
from src.keyboards.registration import slug_confirm_kb, specialty_hints_kb
from src.services.master_registration import MasterRegistrationService
from src.services.slug import SlugService
from src.strings import set_current_lang, strings

router = Router(name="master_registration_v2")


@router.message(MasterRegister.waiting_phone)  # overrides old version
async def register_handle_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    phone = (message.text or "").strip()
    if not phone:
        await message.answer(strings.REGISTER_ASK_PHONE)
        return
    await state.update_data(phone=phone)
    await state.set_state(MasterRegister.waiting_specialty)
    await message.answer(
        strings.REGISTER_ASK_SPECIALTY, reply_markup=specialty_hints_kb()
    )


_HINT_MAP = {
    "hair": "REGISTER_SPECIALTY_HINT_HAIR",
    "dentist": "REGISTER_SPECIALTY_HINT_DENTIST",
    "nails": "REGISTER_SPECIALTY_HINT_NAILS",
    "cosmetologist": "REGISTER_SPECIALTY_HINT_COSMETOLOGIST",
    "custom": "REGISTER_SPECIALTY_HINT_CUSTOM",
}


@router.callback_query(SpecialtyHintCallback.filter(), MasterRegister.waiting_specialty)
async def register_handle_specialty_hint(
    cb: CallbackQuery,
    callback_data: SpecialtyHintCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback_data.hint == "custom":
        await cb.answer()
        if cb.message is not None:
            await cb.message.answer(strings.REGISTER_ASK_SPECIALTY)
        return
    label = getattr(strings, _HINT_MAP[callback_data.hint])
    # Strip emoji prefix — keep only the role text
    stripped = label.split(" ", 1)[1] if " " in label else label
    await _accept_specialty(
        specialty=stripped, state=state, session=session, message=cb.message
    )
    await cb.answer()


@router.message(MasterRegister.waiting_specialty)
async def register_handle_specialty_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    specialty = (message.text or "").strip()
    if not specialty:
        await message.answer(strings.REGISTER_ASK_SPECIALTY)
        return
    await _accept_specialty(
        specialty=specialty, state=state, session=session, message=message
    )


async def _accept_specialty(
    *,
    specialty: str,
    state: FSMContext,
    session: AsyncSession,
    message: Message | None,
) -> None:
    await state.update_data(specialty=specialty)
    data = await state.get_data()
    name: str = data.get("name", "")
    slug_svc = SlugService(session)
    slug = await slug_svc.generate_default(name)
    await state.update_data(proposed_slug=slug)
    await state.set_state(MasterRegister.waiting_slug_confirm)
    if message is not None:
        await message.answer(
            strings.REGISTER_SLUG_CONFIRM_FMT.format(slug=slug),
            reply_markup=slug_confirm_kb(),
        )


@router.callback_query(SlugConfirmCallback.filter(), MasterRegister.waiting_slug_confirm)
async def register_handle_slug_confirm(
    cb: CallbackQuery,
    callback_data: SlugConfirmCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await cb.answer()
    if callback_data.action == "change":
        await state.set_state(MasterRegister.waiting_custom_slug)
        if cb.message is not None:
            await cb.message.answer(strings.REGISTER_ASK_CUSTOM_SLUG)
        return
    # "use"
    data = await state.get_data()
    slug = data["proposed_slug"]
    await _finalize(slug=slug, state=state, session=session, cb=cb)


@router.message(MasterRegister.waiting_custom_slug)
async def register_handle_custom_slug(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
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

    from src.repositories.masters import MasterRepository
    repo = MasterRepository(session)
    if await repo.by_slug(slug) is not None:
        await message.answer(strings.REGISTER_SLUG_TAKEN)
        return

    await _finalize(slug=slug, state=state, session=session, message=message)


async def _finalize(
    *,
    slug: str,
    state: FSMContext,
    session: AsyncSession,
    cb: CallbackQuery | None = None,
    message: Message | None = None,
) -> None:
    data = await state.get_data()
    out_message: Message | None = message
    if out_message is None and cb is not None and cb.message is not None:
        out_message = cb.message  # type: ignore[assignment]

    tg_id: int | None = None
    if cb is not None and cb.from_user is not None:
        tg_id = cb.from_user.id
    elif message is not None and message.from_user is not None:
        tg_id = message.from_user.id
    if tg_id is None:
        await state.clear()
        return

    set_current_lang(data.get("lang", "ru"))

    svc = MasterRegistrationService(session)
    try:
        await svc.register(
            tg_id=tg_id,
            name=data["name"],
            specialty=data["specialty"],
            slug=slug,
            lang=data.get("lang", "ru"),
            invite_code=data["invite_code"],
        )
        await session.commit()
    except SlugTaken:
        if out_message is not None:
            await out_message.answer(strings.REGISTER_SLUG_TAKEN)
        return

    await state.clear()
    if out_message is not None:
        await out_message.answer(strings.REGISTER_DONE, reply_markup=main_menu())
```

- [ ] **Step 4: Обновить `src/handlers/master/__init__.py`**

Подключить `registration_router` ПОСЛЕ `start_router`, чтобы перекрыть старый `register_handle_phone` из `start.py`. Также удалить/заменить старый `register_handle_phone` в `start.py`.

- [ ] **Step 5: Run — expect PASS**

Run: `pytest tests/test_handlers_master_registration.py -v && pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/handlers/master/start.py src/handlers/master/registration.py \
  src/handlers/master/__init__.py tests/test_handlers_master_registration.py
git commit -m "feat(master): invite deep-link + specialty/slug FSM flow"
```

---

### Task 23: Client deep-link + catalog

**Files:**
- Modify: `src/handlers/client/start.py` — разобрать master_<slug> payload + fallback
- Create: `src/handlers/client/catalog.py`
- Modify: `src/handlers/client/__init__.py`
- Test: `tests/test_handlers_client_deep_link.py` (NEW)
- Test: `tests/test_handlers_client_catalog.py` (NEW)

- [ ] **Step 1: Тест deep-link `master_<slug>`**

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Service
from src.handlers.client.start import handle_start


@pytest.mark.asyncio
async def test_valid_master_slug_starts_booking(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="anna-0001")
    session.add(m)
    await session.flush()
    session.add(Service(master_id=m.id, name="cut", duration_min=30))
    await session.commit()

    message = AsyncMock()
    message.text = "/start master_anna-0001"
    message.from_user = AsyncMock(id=999)
    state = AsyncMock()

    await handle_start(
        message=message, master=None, state=state, session=session
    )
    state.update_data.assert_any_call(master_id=str(m.id))


@pytest.mark.asyncio
async def test_unknown_slug_shows_catalog(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="anna-0001")
    session.add(m)
    await session.commit()

    message = AsyncMock()
    message.text = "/start master_nope"
    message.from_user = AsyncMock(id=999)
    state = AsyncMock()

    await handle_start(
        message=message, master=None, state=state, session=session
    )
    # Expected: send CLIENT_MASTER_NOT_FOUND then catalog
    message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_blocked_master_not_bookable(session: AsyncSession) -> None:
    from datetime import datetime, timezone
    m = Master(
        tg_id=1, name="A", slug="blocked-0001",
        blocked_at=datetime.now(timezone.utc),
    )
    session.add(m)
    await session.commit()

    message = AsyncMock()
    message.text = "/start master_blocked-0001"
    message.from_user = AsyncMock(id=999)
    state = AsyncMock()

    await handle_start(
        message=message, master=None, state=state, session=session
    )
    # master_id NOT stored; shown as not-found
    for call in state.update_data.await_args_list:
        assert "master_id" not in call.kwargs
```

- [ ] **Step 2: Обновить `src/handlers/client/start.py`**

```python
from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.fsm.client_booking import ClientBooking
from src.handlers.client.catalog import render_catalog
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
    command: CommandObject | None = None,
) -> None:
    # master (this bot's owner) branch handled earlier — if master is not None
    # and no deep link, master router's handle_start already returned.
    if master is not None:
        return

    payload = command.args if command and command.args else ""
    m_repo = MasterRepository(session)

    if payload.startswith("master_"):
        slug = payload[len("master_"):]
        target = await m_repo.by_slug(slug)
        if target is None or target.blocked_at is not None or not target.is_public:
            await message.answer(strings.CLIENT_MASTER_NOT_FOUND)
            await render_catalog(message=message, session=session)
            return

        s_repo = ServiceRepository(session)
        services = await s_repo.list_active(target.id)
        if not services:
            await message.answer(strings.CLIENT_NO_SERVICES)
            return
        await state.clear()
        await state.set_state(ClientBooking.ChoosingService)
        await state.update_data(master_id=str(target.id))
        await message.answer(
            strings.CLIENT_MASTER_CARD_FMT.format(
                name=target.name, specialty=target.specialty_text or "—"
            )
        )
        await message.answer(
            strings.CLIENT_CHOOSE_SERVICE, reply_markup=services_pick_kb(services)
        )
        return

    # No payload or unrecognized — show catalog
    await render_catalog(message=message, session=session)


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(strings.CLIENT_CANCELLED)
```

- [ ] **Step 3: Реализовать `src/handlers/client/catalog.py`**

```python
from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.catalog import CatalogMasterCallback
from src.fsm.client_booking import ClientBooking
from src.keyboards.catalog import catalog_kb
from src.keyboards.slots import services_pick_kb
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.strings import strings

router = Router(name="client_catalog")


async def render_catalog(*, message: Message, session: AsyncSession) -> None:
    repo = MasterRepository(session)
    masters = await repo.list_public()
    if not masters:
        await message.answer(strings.CLIENT_CATALOG_EMPTY)
        return
    await message.answer(
        strings.CLIENT_CATALOG_HEADER, reply_markup=catalog_kb(masters)
    )


@router.callback_query(CatalogMasterCallback.filter())
async def on_catalog_pick(
    cb: CallbackQuery,
    callback_data: CatalogMasterCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await cb.answer()
    repo = MasterRepository(session)
    master = await repo.by_id(callback_data.master_id)
    if master is None or master.blocked_at is not None:
        if cb.message is not None:
            await cb.message.answer(strings.CLIENT_MASTER_NOT_FOUND)
        return
    s_repo = ServiceRepository(session)
    services = await s_repo.list_active(master.id)
    if not services:
        if cb.message is not None:
            await cb.message.answer(strings.CLIENT_NO_SERVICES)
        return
    await state.clear()
    await state.set_state(ClientBooking.ChoosingService)
    await state.update_data(master_id=str(master.id))
    if cb.message is not None:
        await cb.message.answer(
            strings.CLIENT_CHOOSE_SERVICE, reply_markup=services_pick_kb(services)
        )
```

Также понадобится `MasterRepository.by_id`:

В `src/repositories/masters.py` добавить:

```python
    async def by_id(self, master_id: Any) -> Master | None:
        return cast(Master | None, await self._session.get(Master, master_id))
```

- [ ] **Step 4: Подключить router в `src/handlers/client/__init__.py`**

- [ ] **Step 5: Run — expect PASS**

Run: `pytest tests/test_handlers_client_deep_link.py tests/test_handlers_client_catalog.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/handlers/client/start.py src/handlers/client/catalog.py \
  src/handlers/client/__init__.py src/repositories/masters.py \
  tests/test_handlers_client_deep_link.py tests/test_handlers_client_catalog.py
git commit -m "feat(client): deep-link master_<slug> + fallback catalog"
```

---

### Task 24: Admin router — menu + dispatch

**Files:**
- Create: `src/handlers/admin/__init__.py`
- Create: `src/handlers/admin/menu.py`
- Modify: `src/handlers/__init__.py` (include admin_router ПЕРЕД master_router)
- Test: `tests/test_handlers_admin_menu.py` (NEW)

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.handlers.admin import menu as menu_mod
from src.strings import get_bundle


@pytest.mark.asyncio
async def test_admin_masters_button_dispatches() -> None:
    message = AsyncMock()
    ru = get_bundle("ru")
    message.text = ru.ADMIN_MENU_MASTERS
    session = AsyncMock()

    with patch.object(menu_mod, "cmd_admin_masters", new=AsyncMock()) as mocked:
        await menu_mod.handle_admin_masters(
            message=message, session=session, is_admin=True
        )

    mocked.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_buttons_noop_for_non_admin() -> None:
    message = AsyncMock()
    session = AsyncMock()
    with patch.object(menu_mod, "cmd_admin_masters", new=AsyncMock()) as mocked:
        await menu_mod.handle_admin_masters(
            message=message, session=session, is_admin=False
        )
    mocked.assert_not_awaited()
```

- [ ] **Step 2: Реализовать `src/handlers/admin/menu.py`**

```python
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.handlers.admin.invites_admin import cmd_admin_invites
from src.handlers.admin.masters import cmd_admin_masters
from src.handlers.admin.moderation import cmd_admin_moderation
from src.handlers.admin.stats import cmd_admin_stats
from src.keyboards.common import main_menu
from src.strings import get_bundle, strings

router = Router(name="admin_menu")

_RU = get_bundle("ru")
_HY = get_bundle("hy")


@router.message(F.text.in_({_RU.ADMIN_MENU_MASTERS, _HY.ADMIN_MENU_MASTERS}))
async def handle_admin_masters(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_masters(message=message, session=session)


@router.message(F.text.in_({_RU.ADMIN_MENU_STATS, _HY.ADMIN_MENU_STATS}))
async def handle_admin_stats(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_stats(message=message, session=session)


@router.message(F.text.in_({_RU.ADMIN_MENU_INVITES, _HY.ADMIN_MENU_INVITES}))
async def handle_admin_invites(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_invites(message=message, session=session)


@router.message(F.text.in_({_RU.ADMIN_MENU_MODERATION, _HY.ADMIN_MENU_MODERATION}))
async def handle_admin_moderation(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_moderation(message=message, session=session)


@router.message(F.text.in_({_RU.ADMIN_MENU_BACK, _HY.ADMIN_MENU_BACK}))
async def handle_admin_back(message: Message, is_admin: bool = False) -> None:
    if not is_admin:
        return
    await message.answer(strings.START_WELCOME_BACK, reply_markup=main_menu())
```

- [ ] **Step 3: Stubs для зависимых модулей (удовлетворить импорты)**

Создать skeleton-файлы — заполним в след. задачах. Сначала просто, чтобы импорт не упал:

`src/handlers/admin/masters.py`:

```python
from __future__ import annotations

from aiogram import Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

router = Router(name="admin_masters")


async def cmd_admin_masters(*, message: Message, session: AsyncSession) -> None:
    # Implemented in Task 25
    await message.answer("masters (stub)")
```

Аналогично `src/handlers/admin/stats.py`, `src/handlers/admin/invites_admin.py`, `src/handlers/admin/moderation.py` — каждый с `cmd_admin_*` stub.

- [ ] **Step 4: `src/handlers/admin/__init__.py`**

```python
from __future__ import annotations

from aiogram import Router

from src.handlers.admin.invites_admin import router as invites_router
from src.handlers.admin.masters import router as masters_router
from src.handlers.admin.menu import router as menu_router
from src.handlers.admin.moderation import router as moderation_router
from src.handlers.admin.stats import router as stats_router

router = Router(name="admin")
router.include_router(menu_router)
router.include_router(masters_router)
router.include_router(stats_router)
router.include_router(invites_router)
router.include_router(moderation_router)

__all__ = ["router"]
```

- [ ] **Step 5: Подключить `admin_router` в root**

`src/handlers/__init__.py`:

```python
from src.handlers.admin import router as admin_router
# ...
def build_root_router() -> Router:
    root = Router(name="root")
    root.include_router(admin_router)  # admin first — scoped by is_admin
    root.include_router(master_router)
    root.include_router(client_router)
    return root
```

- [ ] **Step 6: Run**

Run: `pytest tests/test_handlers_admin_menu.py -v && pytest -q`
Expected: всё зелёное (admin-кнопки noop для не-admin).

- [ ] **Step 7: Commit**

```bash
git add src/handlers/admin/ src/handlers/__init__.py \
  tests/test_handlers_admin_menu.py
git commit -m "feat(admin): router skeleton + reply menu dispatch"
```

---

### Task 25: Admin masters — /masters list + detail view

**Files:**
- Modify: `src/handlers/admin/masters.py`
- Test: `tests/test_handlers_admin_masters.py` (NEW)

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.handlers.admin.masters import cmd_admin_masters, cmd_admin_master_detail


@pytest.mark.asyncio
async def test_empty_list(session: AsyncSession) -> None:
    message = AsyncMock()
    await cmd_admin_masters(message=message, session=session)
    message.answer.assert_awaited()
    text = message.answer.await_args[0][0]
    from src.strings import get_bundle
    ru = get_bundle("ru")
    assert ru.ADMIN_MASTERS_EMPTY in text


@pytest.mark.asyncio
async def test_list_shows_all_masters(session: AsyncSession) -> None:
    session.add(Master(tg_id=1, name="A", slug="a-0001"))
    session.add(Master(tg_id=2, name="B", slug="b-0001"))
    await session.commit()

    message = AsyncMock()
    await cmd_admin_masters(message=message, session=session)
    # answer called at least once (header + buttons)
    assert message.answer.await_count >= 1


@pytest.mark.asyncio
async def test_master_detail_by_slug(session: AsyncSession) -> None:
    session.add(Master(tg_id=1, name="A", slug="target-0001", specialty_text="Dentist"))
    await session.commit()

    message = AsyncMock()
    await cmd_admin_master_detail(
        message=message, session=session, slug="target-0001"
    )
    message.answer.assert_awaited()
    sent = message.answer.await_args[0][0]
    assert "target-0001" in sent
    assert "Dentist" in sent


@pytest.mark.asyncio
async def test_master_detail_not_found(session: AsyncSession) -> None:
    message = AsyncMock()
    await cmd_admin_master_detail(
        message=message, session=session, slug="nope"
    )
    message.answer.assert_awaited()
    from src.strings import get_bundle
    ru = get_bundle("ru")
    assert ru.ADMIN_MASTER_NOT_FOUND in message.answer.await_args[0][0]
```

- [ ] **Step 2: Реализовать `src/handlers/admin/masters.py`**

```python
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.admin import block_toggle_kb, masters_list_kb
from src.repositories.masters import MasterRepository
from src.strings import strings

router = Router(name="admin_masters")


async def cmd_admin_masters(*, message: Message, session: AsyncSession) -> None:
    repo = MasterRepository(session)
    masters = await repo.list_all()
    if not masters:
        await message.answer(strings.ADMIN_MASTERS_EMPTY)
        return
    await message.answer(
        strings.ADMIN_MASTERS_HEADER, reply_markup=masters_list_kb(masters)
    )


async def cmd_admin_master_detail(
    *, message: Message, session: AsyncSession, slug: str
) -> None:
    repo = MasterRepository(session)
    master = await repo.by_slug(slug)
    if master is None:
        await message.answer(strings.ADMIN_MASTER_NOT_FOUND)
        return
    is_blocked = master.blocked_at is not None
    status = (
        strings.ADMIN_MASTER_STATUS_BLOCKED
        if is_blocked
        else strings.ADMIN_MASTER_STATUS_ACTIVE
    )
    text = (
        f"*{master.slug}* · {master.name}\n"
        f"Специальность: {master.specialty_text or '—'}\n"
        f"Статус: {status}\n"
        f"Зарегистрирован: {master.created_at.strftime('%Y-%m-%d')}"
    )
    await message.answer(text, reply_markup=block_toggle_kb(master))


@router.message(Command("masters"))
async def handle_masters_cmd(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_masters(message=message, session=session)


@router.message(Command("master"))
async def handle_master_cmd(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return
    slug = (command.args or "").strip()
    if not slug:
        await message.answer("Usage: /master <slug>")
        return
    await cmd_admin_master_detail(message=message, session=session, slug=slug)
```

- [ ] **Step 3: Run — expect PASS**

Run: `pytest tests/test_handlers_admin_masters.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/handlers/admin/masters.py tests/test_handlers_admin_masters.py
git commit -m "feat(admin): /masters list + /master <slug> detail"
```

---

### Task 26: Admin stats — агрегатная статистика

**Files:**
- Modify: `src/handlers/admin/stats.py`
- Test: `tests/test_handlers_admin_stats.py` (NEW)

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.handlers.admin.stats import cmd_admin_stats


@pytest.mark.asyncio
async def test_stats_counts(session: AsyncSession) -> None:
    m1 = Master(tg_id=1, name="A", slug="a-0001")
    m2 = Master(
        tg_id=2, name="B", slug="b-0001",
        blocked_at=datetime.now(timezone.utc),
    )
    session.add_all([m1, m2])
    await session.flush()
    svc = Service(master_id=m1.id, name="cut", duration_min=30)
    cli = Client(master_id=m1.id, name="C", phone="+111", tg_id=999)
    session.add_all([svc, cli])
    await session.flush()

    now = datetime.now(timezone.utc)
    session.add(
        Appointment(
            master_id=m1.id, client_id=cli.id, service_id=svc.id,
            start_at=now, end_at=now + timedelta(hours=1),
            status="confirmed", source="client_request",
            created_at=now - timedelta(days=2),
        )
    )
    session.add(
        Appointment(
            master_id=m1.id, client_id=cli.id, service_id=svc.id,
            start_at=now, end_at=now + timedelta(hours=1),
            status="confirmed", source="client_request",
            created_at=now - timedelta(days=20),
        )
    )
    await session.commit()

    message = AsyncMock()
    await cmd_admin_stats(message=message, session=session)
    text = message.answer.await_args[0][0]
    assert "1" in text  # active masters
    assert "1" in text  # blocked
```

- [ ] **Step 2: Реализовать `src/handlers/admin/stats.py`**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master
from src.strings import strings

router = Router(name="admin_stats")


async def cmd_admin_stats(*, message: Message, session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)

    masters_active = await session.scalar(
        select(func.count(Master.id)).where(Master.blocked_at.is_(None))
    ) or 0
    masters_blocked = await session.scalar(
        select(func.count(Master.id)).where(Master.blocked_at.is_not(None))
    ) or 0
    clients_distinct = await session.scalar(
        select(func.count(distinct(Client.tg_id))).where(Client.tg_id.is_not(None))
    ) or 0
    appt_7d = await session.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.created_at >= now - timedelta(days=7)
        )
    ) or 0
    appt_30d = await session.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.created_at >= now - timedelta(days=30)
        )
    ) or 0

    await message.answer(
        strings.ADMIN_STATS_FMT.format(
            masters_active=masters_active,
            masters_blocked=masters_blocked,
            clients=clients_distinct,
            appt_7d=appt_7d,
            appt_30d=appt_30d,
        )
    )


@router.message(Command("stats"))
async def handle_stats_cmd(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_stats(message=message, session=session)
```

- [ ] **Step 3: Run — expect PASS**

Run: `pytest tests/test_handlers_admin_stats.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/handlers/admin/stats.py tests/test_handlers_admin_stats.py
git commit -m "feat(admin): /stats — aggregate counts for masters/clients/appts"
```

---

### Task 27: Admin invites — список всех

**Files:**
- Modify: `src/handlers/admin/invites_admin.py`
- Test: `tests/test_handlers_admin_invites.py` (NEW)

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite
from src.handlers.admin.invites_admin import cmd_admin_invites


@pytest.mark.asyncio
async def test_admin_invites_lists_all(session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    session.add(
        Invite(code="I1-0001", created_by_tg_id=1, expires_at=now + timedelta(days=7))
    )
    session.add(
        Invite(code="I2-0001", created_by_tg_id=2, expires_at=now + timedelta(days=7))
    )
    await session.commit()

    message = AsyncMock()
    await cmd_admin_invites(message=message, session=session)
    text = message.answer.await_args[0][0]
    assert "I1-0001" in text
    assert "I2-0001" in text
```

- [ ] **Step 2: Реализовать `src/handlers/admin/invites_admin.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite
from src.repositories.invites import InviteRepository
from src.strings import strings

router = Router(name="admin_invites")


def _status(inv: Invite) -> str:
    if inv.used_at is not None:
        return strings.MY_INVITES_STATUS_USED
    if inv.expires_at <= datetime.now(timezone.utc):
        return strings.MY_INVITES_STATUS_EXPIRED
    return strings.MY_INVITES_STATUS_ACTIVE


async def cmd_admin_invites(*, message: Message, session: AsyncSession) -> None:
    repo = InviteRepository(session)
    invites = await repo.list_all()
    if not invites:
        await message.answer(strings.MY_INVITES_EMPTY)
        return
    lines = [strings.ADMIN_INVITES_HEADER]
    for inv in invites:
        lines.append(
            strings.ADMIN_INVITE_ITEM_FMT.format(
                code=inv.code,
                status=_status(inv),
                creator_tg_id=inv.created_by_tg_id,
            )
        )
    await message.answer("\n".join(lines))


@router.message(Command("invites"))
async def handle_invites_cmd(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_invites(message=message, session=session)
```

- [ ] **Step 3: Run — expect PASS**

Run: `pytest tests/test_handlers_admin_invites.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/handlers/admin/invites_admin.py tests/test_handlers_admin_invites.py
git commit -m "feat(admin): /invites — admin view of all invites"
```

---

### Task 28: Moderation — /block, /unblock + client notifications

**Files:**
- Modify: `src/handlers/admin/moderation.py`
- Test: `tests/test_handlers_admin_moderation.py` (NEW)

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.handlers.admin.moderation import cmd_block_master, cmd_unblock_master


@pytest.mark.asyncio
async def test_block_sends_notifications_and_blocks(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="target-0001")
    session.add(m)
    await session.flush()
    svc = Service(master_id=m.id, name="cut", duration_min=30)
    cli = Client(master_id=m.id, name="C", phone="+111", tg_id=987654)
    session.add_all([svc, cli])
    await session.flush()
    now = datetime.now(timezone.utc)
    session.add(
        Appointment(
            master_id=m.id, client_id=cli.id, service_id=svc.id,
            start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=2),
            status="pending", source="client_request",
        )
    )
    await session.commit()

    message = AsyncMock()
    bot = AsyncMock()
    await cmd_block_master(
        message=message, session=session, slug="target-0001", bot=bot
    )
    await session.commit()

    # Bot.send_message called for each client with tg_id
    bot.send_message.assert_awaited()
    await session.refresh(m)
    assert m.blocked_at is not None


@pytest.mark.asyncio
async def test_unblock_clears(session: AsyncSession) -> None:
    m = Master(
        tg_id=1, name="A", slug="target-0001",
        blocked_at=datetime.now(timezone.utc),
    )
    session.add(m)
    await session.commit()

    message = AsyncMock()
    await cmd_unblock_master(
        message=message, session=session, slug="target-0001"
    )
    await session.commit()

    await session.refresh(m)
    assert m.blocked_at is None
```

- [ ] **Step 2: Реализовать `src/handlers/admin/moderation.py`**

```python
from __future__ import annotations

import structlog
from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.admin import admin_menu
from src.repositories.masters import MasterRepository
from src.services.moderation import ModerationService
from src.strings import strings

router = Router(name="admin_moderation")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


async def cmd_admin_moderation(*, message: Message, session: AsyncSession) -> None:
    repo = MasterRepository(session)
    masters = await repo.list_all()
    if not masters:
        await message.answer(strings.ADMIN_MASTERS_EMPTY)
        return
    from src.keyboards.admin import masters_list_kb
    await message.answer(
        strings.ADMIN_MASTERS_HEADER, reply_markup=masters_list_kb(masters)
    )


async def cmd_block_master(
    *,
    message: Message,
    session: AsyncSession,
    slug: str,
    bot: Bot,
) -> None:
    repo = MasterRepository(session)
    master = await repo.by_slug(slug)
    if master is None:
        await message.answer(strings.ADMIN_MASTER_NOT_FOUND)
        return

    svc = ModerationService(session)
    result = await svc.block_master(master.id)

    # Notify clients whose pending got rejected
    for info in result.rejected:
        if info.client_tg_id is None:
            continue
        try:
            await bot.send_message(
                chat_id=info.client_tg_id,
                text=strings.CLIENT_APPT_REJECTED_BLOCK,
            )
        except Exception as e:
            log.warning("notify_failed", tg_id=info.client_tg_id, err=str(e))

    await message.answer(
        strings.ADMIN_BLOCK_DONE_FMT.format(slug=slug, n=len(result.rejected)),
        reply_markup=admin_menu(),
    )


async def cmd_unblock_master(
    *, message: Message, session: AsyncSession, slug: str
) -> None:
    repo = MasterRepository(session)
    master = await repo.by_slug(slug)
    if master is None:
        await message.answer(strings.ADMIN_MASTER_NOT_FOUND)
        return
    svc = ModerationService(session)
    await svc.unblock_master(master.id)
    await message.answer(
        strings.ADMIN_UNBLOCK_DONE_FMT.format(slug=slug),
        reply_markup=admin_menu(),
    )


@router.message(Command("block"))
async def handle_block_cmd(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return
    slug = (command.args or "").strip()
    if not slug:
        await message.answer("Usage: /block <slug>")
        return
    await cmd_block_master(
        message=message, session=session, slug=slug, bot=bot
    )


@router.message(Command("unblock"))
async def handle_unblock_cmd(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return
    slug = (command.args or "").strip()
    if not slug:
        await message.answer("Usage: /unblock <slug>")
        return
    await cmd_unblock_master(message=message, session=session, slug=slug)
```

- [ ] **Step 3: Также реализовать block/unblock через inline-кнопки из masters_list**

В `src/handlers/admin/masters.py` добавить callback:

```python
from aiogram import F
from src.callback_data.admin import AdminMasterCallback, BlockCallback


@router.callback_query(AdminMasterCallback.filter())
async def on_admin_master_view(
    cb: CallbackQuery,
    callback_data: AdminMasterCallback,
    session: AsyncSession,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await cb.answer()
        return
    repo = MasterRepository(session)
    master = await repo.by_id(callback_data.master_id)
    if master is None or cb.message is None:
        await cb.answer()
        return
    await cmd_admin_master_detail(message=cb.message, session=session, slug=master.slug)
    await cb.answer()


@router.callback_query(BlockCallback.filter())
async def on_block_toggle(
    cb: CallbackQuery,
    callback_data: BlockCallback,
    session: AsyncSession,
    bot: Bot,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await cb.answer()
        return
    repo = MasterRepository(session)
    master = await repo.by_id(callback_data.master_id)
    if master is None or cb.message is None:
        await cb.answer()
        return
    if callback_data.block:
        await cmd_block_master(
            message=cb.message, session=session, slug=master.slug, bot=bot
        )
    else:
        await cmd_unblock_master(
            message=cb.message, session=session, slug=master.slug
        )
    await cb.answer()
```

Добавить импорты `CallbackQuery`, `Bot` в masters.py.

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/test_handlers_admin_moderation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/handlers/admin/moderation.py src/handlers/admin/masters.py \
  tests/test_handlers_admin_moderation.py
git commit -m "feat(admin): /block + /unblock with client notifications"
```

---

### Task 29: Blocked master guard — баннер при попытках действий

**Files:**
- Create: `src/middlewares/blocked_guard.py`
- Modify: `src/main.py`
- Test: `tests/test_middleware_blocked_guard.py` (NEW)

Цель: если `master.blocked_at is not None`, заблокировать все master-scope хендлеры (кроме /start и settings-просмотра) с показом баннера.

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from aiogram.types import TelegramObject

from src.db.models import Master
from src.middlewares.blocked_guard import BlockedMasterGuardMiddleware


@dataclass
class FakeMessage:
    text: str
    answer: AsyncMock


@pytest.mark.asyncio
async def test_blocked_master_gets_banner_on_menu_button() -> None:
    master = Master(
        tg_id=1, name="A", slug="a-0001",
        blocked_at=datetime.now(timezone.utc),
    )
    middleware = BlockedMasterGuardMiddleware()
    msg = FakeMessage(text="📅 Сегодня", answer=AsyncMock())
    handler = AsyncMock()

    await middleware(
        handler, cast(TelegramObject, msg), {"master": master}
    )
    handler.assert_not_awaited()
    msg.answer.assert_awaited_once()
    from src.strings import get_bundle
    ru = get_bundle("ru")
    assert ru.MASTER_BLOCKED_BANNER in msg.answer.await_args[0][0]


@pytest.mark.asyncio
async def test_start_passes_through_when_blocked() -> None:
    master = Master(
        tg_id=1, name="A", slug="a-0001",
        blocked_at=datetime.now(timezone.utc),
    )
    middleware = BlockedMasterGuardMiddleware()
    msg = FakeMessage(text="/start", answer=AsyncMock())
    handler = AsyncMock()

    await middleware(
        handler, cast(TelegramObject, msg), {"master": master}
    )
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_active_master_passes_through() -> None:
    master = Master(tg_id=1, name="A", slug="a-0001")
    middleware = BlockedMasterGuardMiddleware()
    msg = FakeMessage(text="📅 Сегодня", answer=AsyncMock())
    handler = AsyncMock()

    await middleware(
        handler, cast(TelegramObject, msg), {"master": master}
    )
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_master_passes_through() -> None:
    middleware = BlockedMasterGuardMiddleware()
    msg = FakeMessage(text="📅 Сегодня", answer=AsyncMock())
    handler = AsyncMock()

    await middleware(
        handler, cast(TelegramObject, msg), {"master": None}
    )
    handler.assert_awaited_once()
```

- [ ] **Step 2: Реализовать `src/middlewares/blocked_guard.py`**

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Final

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from src.strings import strings

_ALLOWED_TEXTS: Final[frozenset[str]] = frozenset({"/start", "/cancel"})


class BlockedMasterGuardMiddleware(BaseMiddleware):
    """Reject all master-scope actions when master.blocked_at is set, showing a banner.

    Allowlist: /start and /cancel so user can at least exit the locked state.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        master = data.get("master")
        if master is None or master.blocked_at is None:
            return await handler(event, data)

        inner: Any = event.event if isinstance(event, Update) else event
        text = getattr(inner, "text", None)
        if isinstance(text, str) and text.strip() in _ALLOWED_TEXTS:
            return await handler(event, data)

        if isinstance(inner, Message):
            await inner.answer(strings.MASTER_BLOCKED_BANNER)
            return None
        return await handler(event, data)
```

- [ ] **Step 3: Зарегистрировать в `src/main.py`**

После `UserMiddleware` и `AdminMiddleware`:

```python
from src.middlewares.blocked_guard import BlockedMasterGuardMiddleware

# ...
    dp.update.middleware(BlockedMasterGuardMiddleware())
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/test_middleware_blocked_guard.py -v && pytest -q`
Expected: всё зелёное.

- [ ] **Step 5: Commit**

```bash
git add src/middlewares/blocked_guard.py src/main.py \
  tests/test_middleware_blocked_guard.py
git commit -m "feat(middleware): BlockedMasterGuard — banner on any locked action"
```

---

### Task 30: Admin /start без мастер-профиля → admin_menu

**Files:**
- Modify: `src/handlers/admin/menu.py` (добавить /start handler для admin-без-master)
- Modify: `src/handlers/master/start.py` (изменить filter)
- Test: `tests/test_handlers_admin_start.py` (NEW)

Цель: пользователь с tg_id в `ADMIN_TG_IDS`, не являющийся мастером, на `/start` получает `admin_menu()` вместо каталога.

- [ ] **Step 1: Тест**

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.handlers.admin.menu import handle_admin_start


@pytest.mark.asyncio
async def test_admin_no_master_sees_admin_menu(session: AsyncSession) -> None:
    message = AsyncMock()
    message.text = "/start"
    state = AsyncMock()

    await handle_admin_start(
        message=message, master=None, state=state,
        session=session, is_admin=True,
    )
    message.answer.assert_awaited()
    # Check reply_markup is admin_menu (reply keyboard)
    kwargs = message.answer.await_args.kwargs
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_admin_with_master_profile_skips_admin_start() -> None:
    from src.db.models import Master
    master = Master(tg_id=1, name="A", slug="a-0001")
    message = AsyncMock()
    state = AsyncMock()

    await handle_admin_start(
        message=message, master=master, state=state,
        session=AsyncMock(), is_admin=True,
    )
    # Delegates to master flow → no answer call here
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_admin_noop() -> None:
    message = AsyncMock()
    state = AsyncMock()
    await handle_admin_start(
        message=message, master=None, state=state,
        session=AsyncMock(), is_admin=False,
    )
    message.answer.assert_not_awaited()
```

- [ ] **Step 2: Добавить handler в `src/handlers/admin/menu.py`**

```python
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.models import Master
from src.keyboards.admin import admin_menu


@router.message(CommandStart())
async def handle_admin_start(
    message: Message,
    master: Master | None,
    state: FSMContext,
    session: AsyncSession,
    is_admin: bool = False,
) -> None:
    # If user is also a master — let master router handle /start (which runs after admin)
    # We only fire for admin-only users (no master row).
    if not is_admin or master is not None:
        return
    await state.clear()
    await message.answer(strings.ADMIN_MENU_TITLE, reply_markup=admin_menu())
```

- [ ] **Step 3: Run — expect PASS**

Run: `pytest tests/test_handlers_admin_start.py -v && pytest -q`
Expected: всё зелёное.

- [ ] **Step 4: Commit**

```bash
git add src/handlers/admin/menu.py tests/test_handlers_admin_start.py
git commit -m "feat(admin): admin-only /start shows admin_menu()"
```

---

### Task 31: setup_bot_commands — scope per role

**Files:**
- Modify: `src/main.py` (расширить _MASTER_COMMANDS + добавить _ADMIN_COMMANDS)
- Modify: `tests/test_main_bot_commands.py`

- [ ] **Step 1: Обновить тесты**

Добавить в `tests/test_main_bot_commands.py`:

```python
@pytest.mark.asyncio
async def test_master_commands_include_epic9_items() -> None:
    bot = AsyncMock()
    bot.set_my_commands = AsyncMock()
    await setup_bot_commands(bot, admin_tg_ids=[123])
    master_ru = next(
        c for c in bot.set_my_commands.call_args_list
        if isinstance(c.kwargs["scope"], BotCommandScopeChat)
        and c.kwargs["language_code"] == "ru"
    )
    names = {cmd.command for cmd in master_ru.kwargs["commands"]}
    assert {"mylink", "myinvites", "new_invite"}.issubset(names)


@pytest.mark.asyncio
async def test_admin_commands_scope_for_admin() -> None:
    bot = AsyncMock()
    bot.set_my_commands = AsyncMock()
    await setup_bot_commands(bot, admin_tg_ids=[555])
    # Admin scope calls should include /masters, /stats, /invites, /block, /unblock
    chat_calls = [
        c for c in bot.set_my_commands.call_args_list
        if isinstance(c.kwargs["scope"], BotCommandScopeChat)
    ]
    ru_call = next(c for c in chat_calls if c.kwargs["language_code"] == "ru")
    names = {cmd.command for cmd in ru_call.kwargs["commands"]}
    # Admin tg_id also is master in practice — commands should include both sets
    assert {"masters", "stats", "invites", "block", "unblock"}.issubset(names)
```

- [ ] **Step 2: Обновить `_MASTER_COMMANDS` и добавить admin commands**

В `src/main.py`:

```python
_MASTER_COMMANDS: dict[str, list[tuple[str, str]]] = {
    "ru": [
        ("start", "Главное меню"),
        ("today", "📅 Расписание на сегодня"),
        ("tomorrow", "📋 Расписание на завтра"),
        ("week", "🗓 Расписание на неделю"),
        ("calendar", "📆 Календарь на месяц"),
        ("add", "Добавить запись вручную"),
        ("client", "🔎 Найти клиента"),
        ("services", "💼 Управление услугами"),
        ("mylink", "🔗 Моя ссылка"),
        ("myinvites", "📨 Мои инвайты"),
        ("new_invite", "Пригласить мастера"),
        ("cancel", "Отменить текущее действие"),
    ],
    "hy": [
        ("start", "Գլխավոր ընտրացանկ"),
        ("today", "📅 Այսօրվա գրաֆիկը"),
        ("tomorrow", "📋 Վաղվա գրաֆիկը"),
        ("week", "🗓 Շաբաթվա գրաֆիկը"),
        ("calendar", "📆 Ամսվա օրացույց"),
        ("add", "Ավելացնել գրանցում ձեռքով"),
        ("client", "🔎 Գտնել հաճախորդ"),
        ("services", "💼 Ծառայությունների կառավարում"),
        ("mylink", "🔗 Իմ հղումը"),
        ("myinvites", "📨 Իմ հրավերները"),
        ("new_invite", "Հրավիրել վարպետ"),
        ("cancel", "Չեղարկել ընթացիկ գործողությունը"),
    ],
}

_ADMIN_EXTRA: dict[str, list[tuple[str, str]]] = {
    "ru": [
        ("masters", "👥 Список мастеров"),
        ("master", "Карточка мастера по slug"),
        ("stats", "📊 Статистика"),
        ("invites", "📨 Все инвайты"),
        ("block", "🚫 Заблокировать мастера"),
        ("unblock", "✅ Разблокировать мастера"),
    ],
    "hy": [
        ("masters", "👥 Վարպետների ցանկ"),
        ("master", "Վարպետի քարտ slug-ով"),
        ("stats", "📊 Վիճակագրություն"),
        ("invites", "📨 Բոլոր հրավերները"),
        ("block", "🚫 Արգելափակել վարպետին"),
        ("unblock", "✅ Վերականգնել վարպետին"),
    ],
}
```

Обновить `setup_bot_commands`:

```python
async def setup_bot_commands(bot: Bot, admin_tg_ids: list[int]) -> None:
    for lang, cmds in _CLIENT_COMMANDS.items():
        await bot.set_my_commands(
            commands=[BotCommand(command=c, description=d) for c, d in cmds],
            scope=BotCommandScopeDefault(),
            language_code=lang,
        )
    for tg_id in admin_tg_ids:
        for lang in ("ru", "hy"):
            merged = _MASTER_COMMANDS[lang] + _ADMIN_EXTRA[lang]
            await bot.set_my_commands(
                commands=[BotCommand(command=c, description=d) for c, d in merged],
                scope=BotCommandScopeChat(chat_id=tg_id),
                language_code=lang,
            )
```

- [ ] **Step 3: Run — expect PASS**

Run: `pytest tests/test_main_bot_commands.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/main.py tests/test_main_bot_commands.py
git commit -m "feat(main): extend bot commands for master + admin scope"
```

---

### Task 32: Финальная проверка — полный прогон тестов + mypy + ruff

**Files:** — (ничего не правим, только валидация)

- [ ] **Step 1: ruff format**

Run: `ruff format .`
Expected: "X files reformatted" или "all good".

- [ ] **Step 2: ruff check**

Run: `ruff check .`
Expected: `All checks passed!` (или исправить оставшееся).

- [ ] **Step 3: mypy strict**

Run: `mypy src/`
Expected: `Success: no issues found in N source files`.

- [ ] **Step 4: Полный прогон тестов**

Run: `pytest -q`
Expected: все тесты зелёные (>= 380 после новых добавлений).

- [ ] **Step 5: Если был lint fix — commit**

```bash
git add -A
git diff --cached --quiet || git commit -m "chore: ruff/mypy cleanup for Epic 9"
```

---

### Task 33: Smoke test — end-to-end сценарии

**Files:** — (ручное тестирование через `alembic upgrade head` + запуск бота локально)

**Подготовка:**
- Остановить любой работающий бот: `docker compose stop bot` (если есть).
- Убедиться что в `.env` правильный `BOT_TOKEN` и `ADMIN_TG_IDS` с твоим tg_id.

- [ ] **Step 1: Применить миграцию на чистую БД**

Run:
```bash
docker compose down -v
docker compose up -d postgres redis
sleep 3
alembic upgrade head
```
Expected: `Running upgrade 0002 -> 0003` успешно.

- [ ] **Step 2: Запустить бота локально**

Run: `python -m src.main`
Expected: лог `bot_starting`.

- [ ] **Step 3: AC #1 — создание инвайта**

- Открыть чат с ботом, `/start`.
- Так как tg_id в ADMIN_TG_IDS, но нет master-записи → получаем `admin_menu()`.
- Нажать `📨 Инвайты` (или `/new_invite` через Menu).

Ожидается: сообщение с кодом `XXXX-YYYY` и ссылкой `t.me/grancvi_bot?start=invite_XXXX-YYYY`.

- [ ] **Step 4: AC #2,3 — регистрация второго мастера по инвайту**

- С другого tg-аккаунта (или в другом клиенте) открыть ссылку инвайта.
- Выбрать язык → ввести имя → ввести телефон → выбрать специальность (кнопка `🦷 Стоматолог`) → подтвердить slug.
- В БД должна появиться запись в `masters` с заполненным slug и specialty_text.

Ожидается: после `REGISTER_DONE` кнопки `main_menu()` с 🔗 Моя ссылка.

- [ ] **Step 5: AC #4 — клиентский deep-link**

- С третьего аккаунта клиента: открыть `t.me/grancvi_bot?start=master_<slug_того_второго>`.
- Увидеть карточку мастера, нажать `📅 Записаться`.

Ожидается: стартует booking flow у правильного мастера. `appointments.master_id` соответствует.

- [ ] **Step 6: AC #5 — каталог**

- С того же клиента: `/start` без payload.
- Увидеть список карточек.

Ожидается: видны оба мастера (admin, если зарегистрирован как master, + второй), отсортированы по `created_at`.

- [ ] **Step 7: AC #6 — один tg_id как клиент у двух мастеров**

- Третий клиент: зарегистрироваться/записаться к обоим мастерам (например, через оба deep-link'а).
- Проверить: `UserMiddleware` не падает (ранее крэшил на `MultipleResultsFound`).

Ожидается: обе записи создались, бот работает.

- [ ] **Step 8: AC #7 — /block**

- С аккаунта админа: `/block <slug_второго_мастера>`.

Ожидается:
- `masters.blocked_at` проставлен.
- pending-записи второго мастера перешли в `rejected`.
- Клиенты получили уведомление `CLIENT_APPT_REJECTED_BLOCK`.
- Второй мастер при попытке `📅 Сегодня` видит баннер `MASTER_BLOCKED_BANNER`.

- [ ] **Step 9: AC #8 — /unblock**

- Админ: `/unblock <slug>`.

Ожидается:
- `blocked_at=NULL`.
- Второй мастер снова может использовать кнопки.
- Отказанные pending НЕ восстановлены (нормально).

- [ ] **Step 10: AC #9 — /masters, /stats, /invites**

- Админ: каждая команда возвращает корректные данные.

Ожидается:
- `/masters` — список с `slug · name · status`.
- `/stats` — числа совпадают с фактом в БД.
- `/invites` — список всех инвайтов + статус.

- [ ] **Step 11: AC #10 — Menu button показывает слэш-команды по scope**

- В клиентском аккаунте (не master, не admin): тапнуть Menu — видно только `/start, /cancel`.
- В мастерском: видно мастерские + `/mylink, /myinvites, /new_invite`.
- В админском: видно те же + `/masters, /master, /stats, /invites, /block, /unblock`.

- [ ] **Step 12: AC #11 — button-dispatch test coverage**

Run: `pytest tests/test_handlers_master_menu_dispatch.py tests/test_handlers_admin_menu.py -v`
Expected: все PASS.

- [ ] **Step 13: AC #12 — data migration корректна**

Run:
```bash
docker compose exec postgres psql -U botik -d botik -c "SELECT tg_id, slug FROM masters"
```
Expected: все мастера имеют непустой slug.

- [ ] **Step 14: AC #13 — линты зелёные (уже сделано в Task 32)**

Проверить вручную если что-то регрессировало во время smoke-теста.

---

### Task 34: Документация + CHANGELOG

**Files:**
- Modify: `BACKLOG.md` — отметить Epic 9 как done.
- (опционально) Create: `CHANGELOG.md` запись.

- [ ] **Step 1: Обновить `BACKLOG.md`**

Найти раздел Epic 9, отметить каждый AC галочкой `[x]`.

- [ ] **Step 2: Commit**

```bash
git add BACKLOG.md CHANGELOG.md
git commit -m "docs: mark Epic 9 multi-master as closed"
```

---

### Task 35: Merge в main + tag v0.9.0-epic-9-multi-master

**Files:** — (git операции)

- [ ] **Step 1: Проверить что всё зелёное**

Run: `ruff check . && mypy src/ && pytest -q`
Expected: всё зелёное.

- [ ] **Step 2: Merge в main**

```bash
git checkout main
git merge --no-ff feature/epic-9-multi-master -m "feat: Epic 9 multi-master v1

- Invite-based master registration with 7-day deep-link codes
- Client deep-link (master_<slug>) + fallback public catalog
- Admin menu with /masters, /stats, /invites, /block, /unblock
- Soft-block moderation: pending rejected, confirmed preserved
- UserMiddleware fix: drop client lookup (multi-master safe)
- Button-first UX per feedback memory"
```

- [ ] **Step 3: Создать тег**

```bash
git tag -a v0.9.0-epic-9-multi-master -m "Epic 9 multi-master v1 — closed"
```

- [ ] **Step 4: Push**

Спросить у пользователя прежде чем push в origin.

---

## Summary

35 задач. Каждая — атомарный коммит с тестами. Ожидаемая длительность при subagent-driven execution: 2-3 рабочих дня.

**Ключевые проверки после выполнения плана:**
- Все 13 AC из `docs/superpowers/specs/2026-04-22-epic-9-multi-master-design.md` проходят.
- `UserMiddleware` multi-master safe (regression test в Task 11).
- Каждая новая команда имеет кнопочный путь (button-dispatch тесты во всех relevant tasks).
- `setup_bot_commands` корректно разграничивает scope'ы (Task 31).
- `BlockedMasterGuard` не даёт блокнутому мастеру выполнять действия (Task 29).
