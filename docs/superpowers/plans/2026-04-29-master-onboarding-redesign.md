# Master Onboarding Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Объединить регистрацию мастера в один TMA-экран, убрать модерацию с критического пути, добавить welcome-экран с QR, поправить копирайт лаунчер-бота и сделать армянский дефолтным языком.

**Architecture:** Координированные изменения в двух репо: `tg-bot` (Python/FastAPI/aiogram) — снимает `is_public=false`, расширяет reserved-slug list, контекстный лаунчер-копирайт; `grancvi-web` (React TMA) — переписывает `RegisterSelf.tsx` с inline-аккордеонами услуг, добавляет `Welcome.tsx`, удаляет `Onboarding.tsx`. Бэк деплоится первым (обратно совместим со старым фронтом), фронт вторым.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, aiogram 3.x, pytest; React 18, react-router-dom, TanStack Query, Vite, Tailwind, qrcode.react.

**Связанная спека:** `docs/superpowers/specs/2026-04-29-master-onboarding-redesign-design.md`

---

## File Structure

### Backend (`tg-bot`)

| Файл | Действие | Ответственность |
|------|----------|-----------------|
| `src/services/master_registration.py` | Modify | Убрать `master.is_public = False`, выставлять `onboarded_at` сразу |
| `src/api/routes/register.py` | Modify | Убрать `salon.is_public = False`; обработать `ReservedSlug`; обновить уведомление админам; тот же `onboarded_at` для салонов в `MeOut` |
| `src/services/slug.py` | Modify | Расширить `_RESERVED` популярными именами |
| `src/app_bot/handlers.py` | Modify | Контекстный `_inline_label_for(payload, lang)`, контекстный welcome-текст, новый `_resolve_lang()`, дефолт армянский |
| `src/repositories/users.py` | Create OR Modify if exists | Lookup сохранённого языка по `tg_id` для `_resolve_lang` (через `Master.lang` пока) |
| `tests/test_services_slug.py` | Modify | Тесты на новые reserved-slugs |
| `tests/test_services_master_registration.py` | Modify | Проверить что `register_self` ставит `is_public=true` + `onboarded_at` |
| `tests/test_app_bot_handlers.py` | Modify | Тесты на контекстный копирайт + дефолт языка |

### Frontend (`grancvi-web`)

| Файл | Действие | Ответственность |
|------|----------|-----------------|
| `src/lib/i18n.ts` | Modify | Дефолт `lang = "hy"`, новые ключи для register/welcome |
| `src/pages/RegisterSelf.tsx` | Rewrite | Один экран: имя+slug+специализации+аккордеоны услуг |
| `src/components/SpecialtyServicesPicker.tsx` | Create | Аккордеон-группы услуг по выбранным специализациям |
| `src/pages/Welcome.tsx` | Create | Экран после регистрации с QR + share buttons |
| `src/App.tsx` | Modify | Добавить `/welcome`, заменить `/onboarding` на soft-redirect, убрать `Navigate to /onboarding` в `RoleRouter` |
| `src/api/hooks.ts` | Modify | Добавить `useBulkCreateServices` (или просто использовать существующий `useCreateService` в цикле) |
| `package.json` | Modify | Добавить `qrcode.react` зависимость |

---

## Phase 1 — Backend (`tg-bot`)

Все задачи фазы 1 коммитятся в репо `tg-bot/`, ветка `feat/onboarding-redesign-backend`.

### Task 1: Создать ветку и подтвердить базовое состояние

**Files:** N/A

- [ ] **Step 1: Убедиться что находимся в `tg-bot/` и main чистый**

Run:
```bash
cd /Users/vanik/Desktop/projects/working-projects/tg-bot
git status
git checkout main
git pull
```
Expected: `working tree clean` или подтверждение что ничего не потеряно.

- [ ] **Step 2: Создать ветку**

Run:
```bash
git checkout -b feat/onboarding-redesign-backend
```

- [ ] **Step 3: Прогнать существующие тесты — baseline**

Run:
```bash
docker compose up -d postgres redis
uv run pytest tests/test_services_master_registration.py tests/test_services_slug.py tests/test_app_bot_handlers.py -v
```
Expected: все проходят.

---

### Task 2: Расширить reserved-slug list

**Files:**
- Modify: `src/services/slug.py:18-59`
- Test: `tests/test_services_slug.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_services_slug.py`:

```python
import pytest

from src.exceptions import ReservedSlug
from src.services.slug import SlugService


@pytest.mark.parametrize(
    "popular_name",
    [
        # Армянские топ-имена
        "anna", "hayk", "narek", "tigran", "armen", "ashot", "vahe",
        "ani", "mariam", "nare", "lilit", "anush", "gohar",
        # Русские топ-имена
        "marina", "elena", "olga", "natalia", "ekaterina", "irina",
        "alex", "andrey", "dmitry", "sergey",
        # Профессиональные общие
        "studio", "salon-anna",  # "salon-anna" должен пройти, но "salon" — нет
    ],
)
def test_validate_rejects_popular_names(popular_name: str) -> None:
    if popular_name == "salon-anna":
        # Sanity — compound должен быть валиден
        SlugService.validate(popular_name)
        return
    with pytest.raises(ReservedSlug):
        SlugService.validate(popular_name)
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run:
```bash
uv run pytest tests/test_services_slug.py::test_validate_rejects_popular_names -v
```
Expected: FAIL (большинство имён не в текущем `_RESERVED`).

- [ ] **Step 3: Расширить `_RESERVED` в `src/services/slug.py:18`**

Заменить блок `_RESERVED = frozenset({...})` (строки 18-59) на:

```python
_RESERVED: Final[frozenset[str]] = frozenset(
    {
        # System / brand / URL routing
        "admin", "bot", "api", "grancvi", "master", "client", "invite",
        "app", "salon", "salons", "m", "s", "register", "preview",
        "media", "static", "assets", "img", "images", "css", "js",
        "www", "mail", "help", "support", "blog", "news", "about",
        "contact", "privacy", "terms", "go", "robots", "sitemap",
        # Popular Armenian first names (top ~30)
        "anna", "ani", "mariam", "lilit", "anush", "gohar", "nare",
        "narine", "nairi", "shushan", "armine",
        "hayk", "narek", "tigran", "armen", "ashot", "vahe", "vahan",
        "aram", "arman", "arsen", "artur", "davit", "gor", "karen",
        "levon", "petros", "rafayel", "samvel", "sargis", "vardan",
        # Popular Russian first names (top ~20)
        "marina", "elena", "olga", "natalia", "natasha", "ekaterina",
        "katya", "irina", "tatyana", "svetlana", "yulia", "anastasia",
        "alex", "andrey", "dmitry", "sergey", "maxim", "ivan", "pavel",
        "roman", "vlad",
        # Common test/dummy values that show up
        "test", "demo", "example", "user", "guest", "anonymous",
    }
)
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run:
```bash
uv run pytest tests/test_services_slug.py::test_validate_rejects_popular_names -v
```
Expected: PASS.

- [ ] **Step 5: Прогнать ВСЕ тесты по slug — убедиться что не сломали существующие**

Run:
```bash
uv run pytest tests/test_services_slug.py tests/test_services_slug_shared_namespace.py -v
```
Expected: все PASS.

- [ ] **Step 6: Коммит**

```bash
git add src/services/slug.py tests/test_services_slug.py
git commit -m "feat(slugs): expand reserved list with popular AM/RU first names"
```

---

### Task 3: Гарантировать что `_resolve_slug` корректно отдаёт `slug_reserved`

**Files:**
- Verify: `src/api/routes/register.py:119-129` (уже ловит через generic `Exception`, но 400 а не 409)
- Modify: `src/api/routes/register.py:122-125`
- Test: `tests/test_api_register.py` (NEW)

- [ ] **Step 1: Создать тест-файл с падающим тестом**

Создать `tests/test_api_register.py`:

```python
"""Coverage for /v1/register/* error mapping (slug_reserved, slug_invalid, slug_taken)."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.main import app


@pytest.mark.asyncio
async def test_register_master_self_rejects_reserved_slug(tg_user_headers, db_session) -> None:
    """A reserved slug must yield HTTP 409 with code='slug_reserved'."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/register/master/self",
            headers=tg_user_headers,
            json={
                "name": "Анна Аракелян",
                "slug": "admin",  # reserved
                "specialty": "hairdresser_women",
                "lang": "hy",
            },
        )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "slug_reserved"
```

Если тест требует фикстур `tg_user_headers` / `db_session`, проверить `tests/conftest.py`. Если их нет — использовать существующий паттерн из `tests/test_api_master.py` (брать оттуда инициализацию).

- [ ] **Step 2: Прогнать тест — должен упасть (ожидаем 409, получаем 400)**

Run:
```bash
uv run pytest tests/test_api_register.py::test_register_master_self_rejects_reserved_slug -v
```
Expected: FAIL — получает 400 (slug_invalid) вместо 409 (slug_reserved).

- [ ] **Step 3: Поправить `_resolve_slug` чтобы отличал ReservedSlug от InvalidSlug**

В `src/api/routes/register.py:119-129` заменить:

```python
async def _resolve_slug(session: AsyncSession, name: str, suggested: str | None) -> str:
    slug_svc = SlugService(session)
    if suggested:
        try:
            SlugService.validate(suggested)
        except Exception as exc:
            raise ApiError("slug_invalid", str(exc), status_code=400) from exc
        if await slug_svc.is_taken(suggested):
            raise ApiError("slug_taken", "slug already taken", status_code=409)
        return suggested
    return await slug_svc.generate_default(name)
```

на:

```python
async def _resolve_slug(session: AsyncSession, name: str, suggested: str | None) -> str:
    slug_svc = SlugService(session)
    if suggested:
        try:
            SlugService.validate(suggested)
        except ReservedSlug as exc:
            raise ApiError("slug_reserved", str(exc), status_code=409) from exc
        except InvalidSlug as exc:
            raise ApiError("slug_invalid", str(exc), status_code=400) from exc
        if await slug_svc.is_taken(suggested):
            raise ApiError("slug_taken", "slug already taken", status_code=409)
        return suggested
    return await slug_svc.generate_default(name)
```

И добавить импорт в шапку файла:

```python
from src.exceptions import InviteAlreadyUsed, InviteExpired, InviteNotFound, InvalidSlug, ReservedSlug, SlugTaken
```

(Дописать `InvalidSlug, ReservedSlug` если их там ещё нет.)

- [ ] **Step 4: Прогнать тест — должен пройти**

Run:
```bash
uv run pytest tests/test_api_register.py -v
```
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/api/routes/register.py tests/test_api_register.py
git commit -m "fix(register): map ReservedSlug to 409 slug_reserved instead of 400"
```

---

### Task 4: Снять модерацию с `register_master_self` + auto-set `onboarded_at`

**Files:**
- Modify: `src/services/master_registration.py:77`
- Modify: `src/services/master_registration.py:85-117` (`_build_master`)
- Test: `tests/test_services_master_registration.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_services_master_registration.py`:

```python
import pytest

from src.services.master_registration import MasterRegistrationService


@pytest.mark.asyncio
async def test_register_self_master_is_public_immediately(db_session) -> None:
    """Self-service registration must NOT land on moderation. is_public=True from creation."""
    svc = MasterRegistrationService(db_session)
    master = await svc.register_self(
        tg_id=99001,
        name="Anna Test",
        specialty="hairdresser_women",
        slug="anna-test-public",
        lang="hy",
    )
    assert master.is_public is True, "self-service registration must skip moderation"


@pytest.mark.asyncio
async def test_register_self_master_marked_onboarded(db_session) -> None:
    """register_self must set onboarded_at — there's no separate Onboarding wizard anymore."""
    svc = MasterRegistrationService(db_session)
    master = await svc.register_self(
        tg_id=99002,
        name="Hayk Test",
        specialty="barber",
        slug="hayk-test-onb",
        lang="hy",
    )
    assert master.onboarded_at is not None, "register_self must auto-set onboarded_at"
```

- [ ] **Step 2: Прогнать тесты — должны упасть**

Run:
```bash
uv run pytest tests/test_services_master_registration.py::test_register_self_master_is_public_immediately tests/test_services_master_registration.py::test_register_self_master_marked_onboarded -v
```
Expected: 1й FAIL (`is_public=False` сейчас), 2й FAIL (`onboarded_at` is None).

- [ ] **Step 3: Удалить `is_public=False` и добавить `onboarded_at`**

В `src/services/master_registration.py:77` удалить строку:

```python
        master.is_public = False  # awaiting admin moderation
```

В `_build_master` (строки 85-117) добавить `onboarded_at=now_utc()` в `Master(...)`:

```python
        return Master(
            tg_id=tg_id,
            name=name,
            slug=slug,
            specialty_text=specialty,
            lang=lang,
            work_hours=default_hours,
            slug_changed_at=now_utc(),
            onboarded_at=now_utc(),  # NEW: registration is the entire onboarding now
        )
```

Обновить docstring `register_self`:

```python
    async def register_self(
        self,
        *,
        tg_id: int,
        name: str,
        specialty: str,
        slug: str,
        lang: str,
    ) -> Master:
        """Self-service registration — no invite required. Master lands
        public (`is_public=True`) and marked onboarded immediately. Slug
        squat-protection is handled by the SlugService reserved-list;
        post-hoc abuse handling via /block.
        """
```

- [ ] **Step 4: Прогнать тесты — должны пройти**

Run:
```bash
uv run pytest tests/test_services_master_registration.py -v
```
Expected: все PASS.

- [ ] **Step 5: Прогнать смежные тесты — может быть какой-нибудь тест ожидает старое поведение**

Run:
```bash
uv run pytest tests/ -k "register or onboard or moderation" -v
```
Expected: PASS. Если что-то падает — это тест на старое поведение `is_public=False`. Проверить, обновить ассерт под новое поведение.

- [ ] **Step 6: Коммит**

```bash
git add src/services/master_registration.py tests/test_services_master_registration.py
git commit -m "feat(register): drop moderation default — masters land is_public=true + onboarded"
```

---

### Task 5: Снять модерацию с `register_salon_self`

**Files:**
- Modify: `src/api/routes/register.py:286-294`
- Test: extend `tests/test_api_register.py`

- [ ] **Step 1: Написать падающий тест**

Добавить в `tests/test_api_register.py`:

```python
@pytest.mark.asyncio
async def test_register_salon_self_is_public_immediately(tg_user_headers) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/register/salon/self",
            headers=tg_user_headers,
            json={"name": "Test Salon Public", "slug": "test-salon-public-x"},
        )
    assert resp.status_code == 201
    me = await ac.get("/v1/me", headers=tg_user_headers)
    assert me.json()["profile"]["is_public"] is True
```

(Если в `MeOut` нет `is_public` для salon — допилить. Альтернативно — проверить через прямой запрос в БД через `db_session` fixture и `select(Salon)`.)

- [ ] **Step 2: Прогнать — должен упасть**

Run:
```bash
uv run pytest tests/test_api_register.py::test_register_salon_self_is_public_immediately -v
```
Expected: FAIL (`is_public=False` сейчас).

- [ ] **Step 3: Удалить `salon.is_public = False`**

В `src/api/routes/register.py:286-294` найти блок:

```python
    try:
        salon = await SalonRepository(session).create(
            owner_tg_id=tg_id, name=payload.name.strip(), slug=slug
        )
    except IntegrityError as exc:
        raise ApiError("slug_taken", "slug already taken", status_code=409) from exc
    salon.is_public = False  # awaiting admin moderation
```

Удалить последнюю строку (`salon.is_public = False`).

- [ ] **Step 4: Прогнать тест — должен пройти**

Run:
```bash
uv run pytest tests/test_api_register.py -v
```
Expected: все PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/api/routes/register.py tests/test_api_register.py
git commit -m "feat(register): drop moderation default for salon self-service too"
```

---

### Task 6: Обновить admin-уведомление — переименовать + новый текст

**Files:**
- Modify: `src/api/routes/register.py:43-77, 172-180, 296-304`

- [ ] **Step 1: Переименовать функцию + обновить копирайт**

В `src/api/routes/register.py:43-77` заменить:

```python
async def _notify_admins_of_moderation(
    *,
    app_bot: Bot | None,
    bot: Bot,
    kind: str,
    name: str,
    slug: str,
    tg_id: int,
    first_name: str,
) -> None:
    """DM each admin with a card about a fresh self-service registration.

    Best-effort: failures (admin never started the bot, transient
    Telegram errors) are swallowed by notify_user so one bad admin
    doesn't break delivery to the others.
    """
    if not settings.admin_tg_ids:
        return
    label = "мастер" if kind == "master" else "салон"
    text = (
        f"🆕 Новый {label} на модерации\n"
        f"👤 {name} (@{first_name}, tg_id={tg_id})\n"
        f"🔗 grancvi.am/{slug}\n\n"
        f"Открой /admin в приложении чтобы одобрить или отклонить."
    )
```

на:

```python
async def _notify_admins_of_new_signup(
    *,
    app_bot: Bot | None,
    bot: Bot,
    kind: str,
    name: str,
    slug: str,
    tg_id: int,
    first_name: str,
) -> None:
    """DM each admin with a heads-up about a fresh self-service registration.

    Self-service skips moderation (master is public on creation), so this
    notification is informational + abuse-handle: if the slug looks
    bad / impersonates someone, admin can /block it.

    Best-effort: failures (admin never started the bot, transient
    Telegram errors) are swallowed by notify_user so one bad admin
    doesn't break delivery to the others.
    """
    if not settings.admin_tg_ids:
        return
    label = "мастер" if kind == "master" else "салон"
    text = (
        f"🆕 Новый {label}\n"
        f"👤 {name} (@{first_name}, tg_id={tg_id})\n"
        f"🔗 grancvi.am/{slug}\n\n"
        f"Если что-то не то — /block {slug}"
    )
```

- [ ] **Step 2: Обновить call-sites**

В `src/api/routes/register.py:172` заменить `_notify_admins_of_moderation(` на `_notify_admins_of_new_signup(`.

В `src/api/routes/register.py:296` (другой call для salon) — то же самое.

- [ ] **Step 3: Прогнать всю тестовую сюиту по register-роутам**

Run:
```bash
uv run pytest tests/test_api_register.py tests/test_services_master_registration.py -v
```
Expected: PASS.

- [ ] **Step 4: Поднять линтеры — убедиться что нет dangling references**

Run:
```bash
uv run ruff check src/api/routes/register.py
uv run mypy src/api/routes/register.py
```
Expected: clean.

- [ ] **Step 5: Коммит**

```bash
git add src/api/routes/register.py
git commit -m "feat(register): rename moderation notification to plain new-signup heads-up"
```

---

### Task 7: Контекстный лаунчер-копирайт + дефолт армянский

**Files:**
- Modify: `src/app_bot/handlers.py`
- Test: `tests/test_app_bot_handlers.py`

- [ ] **Step 1: Написать падающие тесты**

Добавить в `tests/test_app_bot_handlers.py`:

```python
from src.app_bot.handlers import _inline_label_for, _menu_label_for, _resolve_lang_default


def test_inline_label_signup_armenian() -> None:
    assert _inline_label_for("signup", "hy") == "Դառնալ վարպետ"


def test_inline_label_signup_russian() -> None:
    assert _inline_label_for("signup", "ru") == "Стать мастером"


def test_inline_label_signup_salon_armenian() -> None:
    assert _inline_label_for("signup-salon", "hy") == "Գրանցել սրահ"


def test_inline_label_signup_salon_russian() -> None:
    assert _inline_label_for("signup-salon", "ru") == "Зарегистрировать салон"


def test_inline_label_master_link_keeps_booking_copy() -> None:
    """For master_<slug> the button still says 'Записаться' / 'Գրանցվել'."""
    assert _inline_label_for("master_anna-1234", "hy") == "Գրանցվել"
    assert _inline_label_for("master_anna-1234", "ru") == "Записаться"


def test_inline_label_invite() -> None:
    assert _inline_label_for("invite_abc123", "hy") == "Ընդունել հրավերը"
    assert _inline_label_for("invite_abc123", "ru") == "Принять приглашение"


def test_inline_label_no_param() -> None:
    assert _inline_label_for(None, "hy") == "Բացել"
    assert _inline_label_for(None, "ru") == "Открыть"


def test_resolve_lang_default_is_armenian() -> None:
    """Without a saved preference, default is Armenian — NOT Telegram language_code."""
    # No saved lang for tg_id, no override
    assert _resolve_lang_default(saved_lang=None) == "hy"


def test_resolve_lang_default_respects_saved_lang() -> None:
    assert _resolve_lang_default(saved_lang="ru") == "ru"
    assert _resolve_lang_default(saved_lang="en") == "en"
    assert _resolve_lang_default(saved_lang="hy") == "hy"
```

- [ ] **Step 2: Прогнать — все падают (функции с такими сигнатурами не существуют)**

Run:
```bash
uv run pytest tests/test_app_bot_handlers.py -k "inline_label or resolve_lang" -v
```
Expected: FAIL.

- [ ] **Step 3: Переписать `_inline_label_for`, добавить `_resolve_lang_default`, обновить welcome-text**

В `src/app_bot/handlers.py` заменить блок 24-51 (текущие `_menu_label_for`, `_inline_label_for`, `_launch_kb`) на:

```python
def _menu_label_for(lang: str) -> str:
    """Pick the menu-button text from the resolved lang (not from
    Telegram language_code). hy→Հավելված, ru/en→Приложение/App.
    """
    if lang == "hy":
        return "Հավելված"
    if lang == "en":
        return "App"
    return "Приложение"


_INLINE_LABELS: dict[tuple[str, str], str] = {
    # (lang, kind) → label.  kind ∈ {"signup", "signup-salon", "invite",
    # "master_link", "salon_link", "default"}
    ("hy", "signup"): "Դառնալ վարպետ",
    ("ru", "signup"): "Стать мастером",
    ("en", "signup"): "Become a master",
    ("hy", "signup-salon"): "Գրանցել սրահ",
    ("ru", "signup-salon"): "Зарегистрировать салон",
    ("en", "signup-salon"): "Register a salon",
    ("hy", "invite"): "Ընդունել հրավերը",
    ("ru", "invite"): "Принять приглашение",
    ("en", "invite"): "Accept invite",
    ("hy", "master_link"): "Գրանցվել",
    ("ru", "master_link"): "Записаться",
    ("en", "master_link"): "Book",
    ("hy", "salon_link"): "Գրանցվել",
    ("ru", "salon_link"): "Записаться",
    ("en", "salon_link"): "Book",
    ("hy", "default"): "Բացել",
    ("ru", "default"): "Открыть",
    ("en", "default"): "Open",
}


def _kind_for(start_param: str | None) -> str:
    if not start_param:
        return "default"
    if start_param == "signup":
        return "signup"
    if start_param == "signup-salon":
        return "signup-salon"
    if start_param.startswith("invite_"):
        return "invite"
    if start_param.startswith("master_"):
        return "master_link"
    if start_param.startswith("salon_"):
        return "salon_link"
    return "default"


def _inline_label_for(start_param: str | None, lang: str) -> str:
    """CTA-style label for the inline WebApp button under the welcome
    message. Driven by (start_param kind, resolved lang).
    """
    kind = _kind_for(start_param)
    return _INLINE_LABELS.get((lang, kind), _INLINE_LABELS[(lang, "default")])


def _resolve_lang_default(saved_lang: str | None) -> str:
    """Pick the lang for messages BEFORE the user has explicitly chosen
    one in the TMA: armenian-first. Saved preference (from prior TMA
    session, persisted in Master.lang) overrides — but we never fall
    back to Telegram language_code, since that biased non-Armenian
    Telegrams toward Russian.
    """
    if saved_lang in ("ru", "hy", "en"):
        return saved_lang
    return "hy"


def _launch_kb(start_param: str | None, lang: str) -> InlineKeyboardMarkup:
    url = _WEB_APP_URL
    if start_param:
        url = f"{_WEB_APP_URL}?tgWebAppStartParam={start_param}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_inline_label_for(start_param, lang), web_app=WebAppInfo(url=url))]
        ]
    )
```

- [ ] **Step 4: Обновить `handle_start` чтобы использовать `_resolve_lang_default`**

В `src/app_bot/handlers.py:99-117` заменить:

```python
    lang_code = (
        getattr(message.from_user, "language_code", None) if message.from_user is not None else None
    )
    is_hy = (lang_code or "").lower().startswith("hy")
    if is_hy:
        text = (
            "Բացիր գրանցումը մի քանի թափով։\n\n"
            if not start_param
            else "Բաց հավելվածը շարունակելու համար։\n\n"
        )
    else:
        text = (
            "Открой запись в пару тапов.\n\n"
            if not start_param
            else "Открой приложение, чтобы продолжить запись.\n\n"
        )
    _ = settings  # reference kept for future per-env URL config
    await message.answer(text, reply_markup=_launch_kb(start_param, lang_code))
```

на:

```python
    saved_lang = await _lookup_saved_lang(session, user_tg_id) if user_tg_id is not None else None
    lang = _resolve_lang_default(saved_lang)
    text = _welcome_text_for(start_param, lang)
    await message.answer(text, reply_markup=_launch_kb(start_param, lang))
```

И добавить в файл (после `_resolve_lang_default`):

```python
_WELCOME_TEXTS: dict[tuple[str, str], str] = {
    ("hy", "default"): "Բացիր Grancvi-ն.",
    ("ru", "default"): "Открой Grancvi.",
    ("en", "default"): "Open Grancvi.",
    ("hy", "signup"): "Վարպետի գրանցում՝ մի քանի թափով.",
    ("ru", "signup"): "Регистрация мастера — пара тапов.",
    ("en", "signup"): "Master registration — a couple of taps.",
    ("hy", "signup-salon"): "Սրահի գրանցում՝ մի քանի թափով.",
    ("ru", "signup-salon"): "Регистрация салона — пара тапов.",
    ("en", "signup-salon"): "Salon registration — a couple of taps.",
    ("hy", "invite"): "Բացիր հավելվածը՝ հրավերն ընդունելու համար.",
    ("ru", "invite"): "Открой приложение чтобы принять приглашение.",
    ("en", "invite"): "Open the app to accept the invite.",
    ("hy", "master_link"): "Բացիր հավելվածը՝ գրանցվելու համար.",
    ("ru", "master_link"): "Открой приложение чтобы записаться.",
    ("en", "master_link"): "Open the app to book.",
    ("hy", "salon_link"): "Բացիր հավելվածը՝ գրանցվելու համար.",
    ("ru", "salon_link"): "Открой приложение чтобы записаться.",
    ("en", "salon_link"): "Open the app to book.",
}


def _welcome_text_for(start_param: str | None, lang: str) -> str:
    kind = _kind_for(start_param)
    return _WELCOME_TEXTS.get((lang, kind), _WELCOME_TEXTS[(lang, "default")])


async def _lookup_saved_lang(session: AsyncSession | None, tg_id: int) -> str | None:
    """Best-effort: read the user's last-used lang from the masters
    table. Returns None if the user is not yet a master or session
    isn't available."""
    if session is None:
        return None
    from src.db.models import Master  # local import to avoid cycle

    row = await session.scalar(select(Master.lang).where(Master.tg_id == tg_id))
    return row
```

И обеспечить импорты в шапке:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
```

- [ ] **Step 5: Обновить также `set_chat_menu_button` чтобы использовал resolved lang**

В `src/app_bot/handlers.py:125-135` заменить:

```python
        label = _menu_label_for(lang_code)
```

на:

```python
        label = _menu_label_for(lang)
```

(Переменная `lang` уже доступна из `_resolve_lang_default` выше.)

Удалить теперь неиспользуемое:
```python
    lang_code = (
        getattr(message.from_user, "language_code", None) if message.from_user is not None else None
    )
```

- [ ] **Step 6: Подключить session DI в `handle_start`**

Найти сигнатуру `handle_start`:

```python
@router.message(CommandStart())
async def handle_start(
    message: Message,
    bot: Bot,
    command: CommandObject | None = None,
) -> None:
```

Добавить параметр `session: AsyncSession`:

```python
@router.message(CommandStart())
async def handle_start(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    command: CommandObject | None = None,
) -> None:
```

(aiogram middleware `db.py` уже инжектит session — это обычный паттерн в codebase.)

- [ ] **Step 7: Прогнать тесты — должны пройти**

Run:
```bash
uv run pytest tests/test_app_bot_handlers.py -v
```
Expected: PASS.

- [ ] **Step 8: Линтеры**

Run:
```bash
uv run ruff check src/app_bot/handlers.py
uv run mypy src/app_bot/handlers.py
```
Expected: clean.

- [ ] **Step 9: Коммит**

```bash
git add src/app_bot/handlers.py tests/test_app_bot_handlers.py
git commit -m "feat(app_bot): context-aware launcher copy + Armenian default lang"
```

---

### Task 8: Финальная сборка фазы 1 — все тесты + push

- [ ] **Step 1: Прогнать всю тестовую сюиту**

Run:
```bash
uv run pytest -v
```
Expected: PASS.

- [ ] **Step 2: Линт + типы**

Run:
```bash
uv run ruff check . && uv run ruff format . && uv run mypy src/
```
Expected: clean.

- [ ] **Step 3: Запушить ветку**

Run:
```bash
git push -u origin feat/onboarding-redesign-backend
```

- [ ] **Step 4: Дождаться апрува пользователя на содержимое ветки**

Сообщить пользователю: «Бэкенд-ветка `feat/onboarding-redesign-backend` готова. Проверь diff: `git diff main...feat/onboarding-redesign-backend`. Когда ок — деплоим бэк и переходим к фронту.»

---

## Phase 2 — Frontend (`grancvi-web`)

Все задачи фазы 2 коммитятся в репо `grancvi-web/` (sibling). Ветка `feat/onboarding-redesign`.

### Task 9: Создать ветку, baseline проверка

**Files:** N/A

- [ ] **Step 1: Перейти в репо и создать ветку**

Run:
```bash
cd /Users/vanik/Desktop/projects/working-projects/grancvi-web
git status
git checkout main
git pull
git checkout -b feat/onboarding-redesign
```

- [ ] **Step 2: Установить зависимости (если нужно)**

Run:
```bash
pnpm install
```
Expected: clean install.

- [ ] **Step 3: Убедиться что dev-сервер стартует**

Run:
```bash
pnpm dev
```
Expected: Vite поднимается на `http://localhost:5173`. Открыть, убедиться что текущая `RegisterSelf` рендерится.

Остановить (`Ctrl+C`).

---

### Task 10: Установить `qrcode.react`

**Files:**
- Modify: `package.json`

- [ ] **Step 1: Поставить пакет**

Run:
```bash
pnpm add qrcode.react
```
Expected: `qrcode.react` появляется в `dependencies` в `package.json`. Проверить что зависимость лёгкая (без излишних peer-deps).

- [ ] **Step 2: Коммит**

```bash
git add package.json pnpm-lock.yaml
git commit -m "deps: add qrcode.react for welcome-screen QR rendering"
```

---

### Task 11: Дефолт `lang = "hy"` в i18n

**Files:**
- Modify: `src/lib/i18n.ts:469-480`

- [ ] **Step 1: Поправить `detectInitialLang`**

Заменить:

```typescript
function detectInitialLang(): Lang {
  const stored = typeof localStorage !== "undefined" && localStorage.getItem(STORAGE_KEY);
  if (stored === "ru" || stored === "hy") return stored;
  try {
    const lp = retrieveLaunchParams(true);
    const code = lp.tgWebAppData?.user?.languageCode;
    if (code === "hy") return "hy";
  } catch {
    // outside Telegram
  }
  return "ru";
}
```

на:

```typescript
function detectInitialLang(): Lang {
  // Saved preference always wins.
  const stored = typeof localStorage !== "undefined" && localStorage.getItem(STORAGE_KEY);
  if (stored === "ru" || stored === "hy") return stored;
  // Armenia-first product: default to Armenian for any new user.
  // Telegram language_code is intentionally ignored — Armenians with
  // Russian/English Telegram clients should still land in Armenian UI
  // unless they pick another language explicitly.
  return "hy";
}
```

- [ ] **Step 2: Запустить dev, проверить визуально**

Run:
```bash
pnpm dev
```

Открыть `http://localhost:5173/` в браузере, **очистить localStorage** (DevTools → Application → Local Storage → clear), перезагрузить.

Expected: интерфейс на армянском.

- [ ] **Step 3: Коммит**

```bash
git add src/lib/i18n.ts
git commit -m "feat(i18n): default lang to Armenian (Armenia-first)"
```

---

### Task 12: Добавить новые i18n ключи для register/welcome

**Files:**
- Modify: `src/lib/i18n.ts` (раздел `translations`)

- [ ] **Step 1: Добавить ключи в объект `translations`**

В `src/lib/i18n.ts` найти раздел с переводами (около строки 80, объект с ключами `nav.*`, `register.*`, etc.) и добавить:

```typescript
  // Register-self redesign
  self_register_v2_title: { ru: "Регистрация мастера", hy: "Վարպետի գրանցում", en: "Master registration" },
  self_register_v2_intro: {
    ru: "Заполни три поля и начни принимать клиентов.",
    hy: "Լրացրու երեք դաշտը և սկսիր ընդունել հաճախորդներին.",
    en: "Fill three fields and start accepting clients.",
  },
  self_register_v2_specialty_label: {
    ru: "Чем занимаешься?",
    hy: "Ինչո՞վ ես զբաղվում.",
    en: "What do you do?",
  },
  self_register_v2_services_header_fmt: {
    ru: "Услуги — {n} выбрано",
    hy: "Ծառայություններ — {n} ընտրված",
    en: "Services — {n} selected",
  },
  self_register_v2_services_empty: {
    ru: "Выбери специализацию выше, чтобы увидеть услуги.",
    hy: "Ընտրիր մասնագիտություն վերևում՝ ծառայությունները տեսնելու համար.",
    en: "Pick a specialty above to see services.",
  },
  self_register_v2_add_custom: {
    ru: "+ Своя услуга",
    hy: "+ Սեփական ծառայություն",
    en: "+ Custom service",
  },
  self_register_v2_submit_fmt: {
    ru: "Готов начинать · {n} услуг",
    hy: "Պատրաստ եմ սկսել · {n} ծառայություն",
    en: "Ready to start · {n} services",
  },
  self_register_v2_specialty_too_many: {
    ru: "Совет: выбери 1–3 — клиенту проще понять.",
    hy: "Խորհուրդ՝ ընտրիր 1–3-ը՝ հաճախորդի համար ավելի հասկանալի կլինի.",
    en: "Tip: pick 1-3 — easier for the client to grasp.",
  },

  // Welcome screen
  welcome_title_fmt: {
    ru: "Привет, {name}!",
    hy: "Բարև, {name}!",
    en: "Hi, {name}!",
  },
  welcome_subtitle: {
    ru: "Твоя страница готова. Поделись ссылкой — клиенты записываются за 3 секунды.",
    hy: "Քո էջը պատրաստ է. Կիսվիր հղումով — հաճախորդները գրանցվում են 3 վայրկյանում.",
    en: "Your page is live. Share the link — clients book in 3 seconds.",
  },
  welcome_copy_link: { ru: "Скопировать ссылку", hy: "Պատճենել հղումը", en: "Copy link" },
  welcome_copy_done: { ru: "Скопировано", hy: "Պատճենվեց", en: "Copied" },
  welcome_share_tg: {
    ru: "Поделиться в Telegram",
    hy: "Կիսվել Telegram-ով",
    en: "Share on Telegram",
  },
  welcome_share_message: {
    ru: "Запиши себя ко мне через Grancvi:",
    hy: "Գրանցիր ինձ մոտ Grancvi-ի միջոցով:",
    en: "Book me via Grancvi:",
  },
  welcome_what_next: { ru: "Что дальше:", hy: "Ի՞նչ է հաջորդը.", en: "What's next:" },
  welcome_tip_print: {
    ru: "Распечатай QR и повесь в кабинете",
    hy: "Տպիր QR-ը և փակցրու կաբինետում",
    en: "Print the QR and stick it in your studio",
  },
  welcome_tip_instagram: {
    ru: "Добавь ссылку в профиль Instagram",
    hy: "Ավելացրու հղումը Instagram-ի պրոֆիլում",
    en: "Add the link to your Instagram profile",
  },
  welcome_tip_help: {
    ru: "Можем приехать и наклеить QR — напиши @grancvi_help",
    hy: "Կարող ենք գալ և փակցնել QR-ը — գրիր @grancvi_help",
    en: "We can come and stick the QR — message @grancvi_help",
  },
  welcome_to_dashboard: {
    ru: "В мой кабинет",
    hy: "Իմ կաբինետ",
    en: "Go to my dashboard",
  },
```

- [ ] **Step 2: Скомпилировать, убедиться что нет ошибок типизации**

Run:
```bash
pnpm exec tsc -b --noEmit
```
Expected: clean.

- [ ] **Step 3: Коммит**

```bash
git add src/lib/i18n.ts
git commit -m "feat(i18n): add register-v2 + welcome screen translations"
```

---

### Task 13: Создать `SpecialtyServicesPicker` компонент

**Files:**
- Create: `src/components/SpecialtyServicesPicker.tsx`

- [ ] **Step 1: Реализовать компонент**

Создать файл `src/components/SpecialtyServicesPicker.tsx`:

```typescript
import { useState } from "react";

import { useLang } from "../lib/i18n";
import {
  SERVICE_PRESETS,
  type SpecialtyCode,
  isSpecialtyCode,
} from "../lib/specialties";

export type PickedService = {
  preset_id: string;
  name: string;
  duration_min: number;
};

type Props = {
  selectedSpecialties: string[]; // ordered: first-picked is first
  selectedServiceIds: Set<string>;
  onToggleService: (presetId: string) => void;
};

/**
 * Accordion of service presets grouped by specialty. The first
 * specialty added is auto-expanded; subsequent ones are collapsed by
 * default. The caller owns selection state — this component only
 * reflects/toggles via callbacks.
 */
export function SpecialtyServicesPicker({
  selectedSpecialties,
  selectedServiceIds,
  onToggleService,
}: Props) {
  const { t, lang } = useLang();
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(selectedSpecialties.length > 0 ? [selectedSpecialties[0]] : []),
  );

  if (selectedSpecialties.length === 0) {
    return (
      <p className="text-sm text-tg-hint py-2">
        {t("self_register_v2_services_empty")}
      </p>
    );
  }

  function toggleExpand(code: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  return (
    <div className="space-y-2">
      {selectedSpecialties.map((code) => {
        if (!isSpecialtyCode(code)) return null;
        const presets = SERVICE_PRESETS[code as SpecialtyCode] ?? [];
        const total = presets.length;
        const picked = presets.filter((p) => selectedServiceIds.has(p.id)).length;
        const isOpen = expanded.has(code);

        return (
          <div
            key={code}
            className="rounded-2xl bg-white/60 dark:bg-white/5 border border-black/5 dark:border-white/10 overflow-hidden"
          >
            <button
              type="button"
              onClick={() => toggleExpand(code)}
              className="w-full flex items-center justify-between px-4 py-3 active:opacity-70"
            >
              <div className="flex items-center gap-2">
                <span className="text-tg-hint text-xs">{isOpen ? "▼" : "▶"}</span>
                <span className="font-medium text-sm">
                  {lang === "hy" ? specialtyLabel(code, "hy") : specialtyLabel(code, "ru")}
                </span>
              </div>
              <span className="text-xs text-tg-hint">{picked} / {total}</span>
            </button>
            {isOpen && (
              <ul className="border-t border-black/5 dark:border-white/10 divide-y divide-black/5 dark:divide-white/5">
                {presets.map((p) => {
                  const checked = selectedServiceIds.has(p.id);
                  return (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => onToggleService(p.id)}
                        className="w-full flex items-center justify-between px-4 py-2.5 active:opacity-70"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span
                            className={`w-5 h-5 rounded-md grid place-items-center text-[10px] font-bold shrink-0 ${
                              checked
                                ? "bg-tg-button text-tg-button-text"
                                : "bg-white/80 dark:bg-black/20 border border-black/10 dark:border-white/10 text-transparent"
                            }`}
                          >
                            ✓
                          </span>
                          <span className="text-sm text-tg-text truncate">
                            {lang === "hy" ? p.hy : p.ru}
                          </span>
                        </div>
                        <span className="text-xs text-tg-hint shrink-0">
                          {p.duration_min}м
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

// Local helper — show specialty name for the accordion header. The
// real specialty list is loaded via useSpecialties() at form level,
// but we don't want a second fetch here, so we inline the labels.
function specialtyLabel(code: string, lang: "ru" | "hy"): string {
  // This function is intentionally tiny — full labels live in the
  // backend specialties table. For the picker header we accept the
  // raw code as a fallback if it's not in our local map.
  const LOCAL_LABELS: Record<string, { ru: string; hy: string }> = {
    hairdresser_women: { ru: "Парикмахер женский", hy: "Կանացի վարսահարդար" },
    hairdresser_men: { ru: "Парикмахер мужской", hy: "Տղամարդկանց վարսավիր" },
    hairdresser_uni: { ru: "Парикмахер универсал", hy: "Վարսահարդար" },
    barber: { ru: "Барбер", hy: "Բարբեր" },
    colorist: { ru: "Колорист", hy: "Կոլորիստ" },
    nails_manicure: { ru: "Маникюр", hy: "Մանիկյուր" },
    nails_pedicure: { ru: "Педикюр", hy: "Պեդիկյուր" },
    brows: { ru: "Брови", hy: "Հոնքեր" },
    lashes: { ru: "Ресницы", hy: "Թարթիչներ" },
    makeup: { ru: "Макияж", hy: "Դիմահարդարում" },
    cosmetology: { ru: "Косметология", hy: "Կոսմետոլոգիա" },
    massage: { ru: "Массаж", hy: "Մերսում" },
    depilation: { ru: "Депиляция", hy: "Մազահեռացում" },
    dentist: { ru: "Стоматолог", hy: "Ատամնաբույժ" },
    other: { ru: "Другое", hy: "Այլ" },
  };
  return LOCAL_LABELS[code]?.[lang] ?? code;
}
```

**Замечание:** `specialtyLabel` дублирует данные из `useSpecialties()`. Если позже сделаешь чище — вынеси в общий `lib/specialties.ts`. Сейчас inline для скорости.

- [ ] **Step 2: Скомпилировать**

Run:
```bash
pnpm exec tsc -b --noEmit
```
Expected: clean.

- [ ] **Step 3: Коммит**

```bash
git add src/components/SpecialtyServicesPicker.tsx
git commit -m "feat(register): add SpecialtyServicesPicker accordion component"
```

---

### Task 14: Переписать `RegisterSelf.tsx` под новый дизайн

**Files:**
- Modify (full rewrite): `src/pages/RegisterSelf.tsx`

- [ ] **Step 1: Заменить содержимое полностью**

Полное содержимое `src/pages/RegisterSelf.tsx`:

```typescript
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  useCreateService,
  useMarkOnboarded,
  useRegisterMasterSelf,
  useSpecialties,
} from "../api/hooks";
import { errorMessage } from "../components/ErrorState";
import { Layout } from "../components/Layout";
import { SlugInput } from "../components/SlugInput";
import { SpecialtyServicesPicker } from "../components/SpecialtyServicesPicker";
import { isTMA } from "../lib/isTMA";
import { transliterate } from "../lib/transliterate";
import { useLang } from "../lib/i18n";
import {
  SERVICE_PRESETS,
  type SpecialtyCode,
  isSpecialtyCode,
} from "../lib/specialties";
import { useMainButton } from "../lib/useMainButton";

/**
 * Self-service master registration — single screen.
 *
 *   1. Name + slug
 *   2. Specialties (multi-select chips)
 *   3. Services accordion — auto-revealed per specialty, all presets
 *      pre-checked, master un-ticks anything they don't do
 *   4. TG MainButton submits everything in one go: register + bulk
 *      service POSTs + mark onboarded → /welcome
 *
 * No moderation: master lands `is_public=true` and can share QR
 * immediately. Reserved-slug protection lives on the backend.
 */
export function RegisterSelf() {
  const { t, lang } = useLang();
  const navigate = useNavigate();
  const register = useRegisterMasterSelf();
  const createService = useCreateService();
  const markOnboarded = useMarkOnboarded();
  const specialtyList = useSpecialties();

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  // Ordered: first-picked first → drives accordion-expand default
  const [specialties, setSpecialties] = useState<string[]>([]);
  // Selected service preset ids across all picked specialties
  const [serviceIds, setServiceIds] = useState<Set<string>>(new Set());

  // Whenever the user picks a new specialty, pre-select all its presets.
  // Whenever they remove a specialty, drop those presets too.
  function toggleSpecialty(code: string) {
    setSpecialties((prev) => {
      const has = prev.includes(code);
      const nextList = has ? prev.filter((c) => c !== code) : [...prev, code];

      setServiceIds((prevIds) => {
        const next = new Set(prevIds);
        if (!isSpecialtyCode(code)) return next;
        const presets = SERVICE_PRESETS[code as SpecialtyCode] ?? [];
        if (has) {
          // Removing — drop ids that aren't covered by any other still-picked specialty
          const stillPicked = nextList.filter(isSpecialtyCode) as SpecialtyCode[];
          const stillCoveredIds = new Set(
            stillPicked.flatMap((c) => SERVICE_PRESETS[c].map((p) => p.id)),
          );
          for (const p of presets) {
            if (!stillCoveredIds.has(p.id)) next.delete(p.id);
          }
        } else {
          // Adding — pre-select all of this specialty's presets
          for (const p of presets) next.add(p.id);
        }
        return next;
      });

      return nextList;
    });
  }

  function toggleService(presetId: string) {
    setServiceIds((prev) => {
      const next = new Set(prev);
      if (next.has(presetId)) next.delete(presetId);
      else next.add(presetId);
      return next;
    });
  }

  // Map selected ids → actual preset records (for POST). Dedupe across
  // overlapping specialties (e.g. `coloring` exists in both
  // hairdresser_women and colorist).
  const selectedPresets = useMemo(() => {
    const seen = new Map<string, { id: string; ru: string; hy: string; duration_min: number }>();
    for (const code of specialties) {
      if (!isSpecialtyCode(code)) continue;
      for (const p of SERVICE_PRESETS[code as SpecialtyCode] ?? []) {
        if (serviceIds.has(p.id) && !seen.has(p.id)) seen.set(p.id, p);
      }
    }
    return Array.from(seen.values());
  }, [specialties, serviceIds]);

  const canSubmit =
    !!name.trim() &&
    specialties.length > 0 &&
    selectedPresets.length > 0 &&
    !register.isPending &&
    !createService.isPending &&
    !markOnboarded.isPending;

  async function submit() {
    if (!canSubmit) return;
    try {
      // 1. Register the master.
      await register.mutateAsync({
        name: name.trim(),
        specialty: specialties.join(","),
        slug: slug.trim() || null,
        lang: lang === "hy" ? "hy" : "ru",
      });

      // 2. Bulk-create services (sequential — back-end does its own
      // validation per row; few dozen at most).
      for (const p of selectedPresets) {
        const localizedName = lang === "hy" ? p.hy : p.ru;
        await createService.mutateAsync({
          name: localizedName,
          duration_min: p.duration_min,
          price_amd: null,
          preset_code: p.id,
        });
      }

      // 3. Mark onboarded — guard against backend not auto-setting
      // (it does after Phase 1, but harmless to call again).
      try {
        await markOnboarded.mutateAsync();
      } catch {
        // already onboarded — ignore
      }

      try {
        sessionStorage.setItem("grancvi.startParamConsumed", "1");
      } catch {
        /* ignore */
      }
      navigate("/welcome", { replace: true });
    } catch {
      // surfaced via register.error / createService.error
    }
  }

  const submitText = t("self_register_v2_submit_fmt", {
    n: selectedPresets.length,
  });

  useMainButton({
    text: register.isPending || createService.isPending ? t("form_submitting") : submitText,
    enabled: canSubmit,
    loading: register.isPending || createService.isPending,
    visible: canSubmit || register.isPending || createService.isPending,
    onClick: submit,
  });

  const tooManySpecialties = specialties.length > 3;

  return (
    <Layout title={t("self_register_v2_title")}>
      <div className="p-6 space-y-5">
        <p className="text-sm text-tg-hint leading-relaxed">
          {t("self_register_v2_intro")}
        </p>

        <Field label={t("register_name_label")}>
          <input
            value={name}
            onChange={(e) => {
              const v = e.target.value;
              setName(v);
              if (!slugTouched) setSlug(transliterate(v));
            }}
            maxLength={200}
            className="w-full rounded-xl bg-white/80 dark:bg-black/20 border border-black/5 dark:border-white/10 px-3 py-2"
          />
        </Field>

        <Field label={t("profile_slug_label")} hint={t("slug_change_cooldown_hint")}>
          <SlugInput
            value={slug}
            onChange={(v) => {
              setSlug(v);
              setSlugTouched(true);
            }}
          />
        </Field>

        <div className="space-y-2">
          <span className="text-xs text-tg-hint">{t("self_register_v2_specialty_label")}</span>
          <div className="flex flex-wrap gap-2">
            {(specialtyList.data ?? []).map((s) => {
              const checked = specialties.includes(s.code);
              return (
                <button
                  key={s.code}
                  type="button"
                  onClick={() => toggleSpecialty(s.code)}
                  className={`rounded-full px-3 py-1.5 text-xs font-medium transition active:opacity-70 ${
                    checked
                      ? "bg-tg-button text-tg-button-text"
                      : "bg-white/80 dark:bg-black/20 border border-black/10 dark:border-white/10 text-tg-text"
                  }`}
                >
                  {checked ? "● " : "○ "}
                  {lang === "hy" ? s.name_hy : s.name_ru}
                </button>
              );
            })}
          </div>
          {tooManySpecialties && (
            <p className="text-[11px] text-amber-600 dark:text-amber-400">
              {t("self_register_v2_specialty_too_many")}
            </p>
          )}
        </div>

        {specialties.length > 0 && (
          <div className="space-y-3">
            <h2 className="text-sm font-semibold text-tg-text">
              {t("self_register_v2_services_header_fmt", { n: selectedPresets.length })}
            </h2>
            <SpecialtyServicesPicker
              selectedSpecialties={specialties}
              selectedServiceIds={serviceIds}
              onToggleService={toggleService}
            />
            {/* Custom-service entry stays as a simple link to the post-
                register editor — out of registration scope. */}
            <p className="text-xs text-tg-hint">
              {t("self_register_v2_add_custom")} — позже в редакторе услуг
            </p>
          </div>
        )}

        {register.error && (
          <div className="rounded-xl bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-300 px-4 py-3 text-sm">
            {errorMessage(register.error, t)}
          </div>
        )}

        {!isTMA() && (
          <button
            type="button"
            disabled={!canSubmit}
            onClick={submit}
            className="w-full rounded-xl bg-tg-button text-tg-button-text px-4 py-3 text-sm font-semibold active:opacity-80 disabled:opacity-50"
          >
            {register.isPending || createService.isPending
              ? t("form_submitting")
              : submitText}
          </button>
        )}
      </div>
    </Layout>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs text-tg-hint">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-tg-hint">{hint}</span>}
    </label>
  );
}
```

- [ ] **Step 2: Скомпилировать**

Run:
```bash
pnpm exec tsc -b --noEmit
```
Expected: clean. Если есть ошибки про несуществующий хук `useCreateService` или `useMarkOnboarded` — открыть `src/api/hooks.ts` и убедиться что они есть. Если нет — создать (см. Task 15 ниже как приложение).

- [ ] **Step 3: Коммит**

```bash
git add src/pages/RegisterSelf.tsx
git commit -m "feat(register): rewrite RegisterSelf as single-screen with inline services"
```

---

### Task 15: Создать `Welcome.tsx`

**Files:**
- Create: `src/pages/Welcome.tsx`

- [ ] **Step 1: Реализовать страницу**

Создать `src/pages/Welcome.tsx`:

```typescript
import { useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { useNavigate } from "react-router-dom";

import { useMe } from "../api/hooks";
import { Layout } from "../components/Layout";
import { isTMA } from "../lib/isTMA";
import { useLang } from "../lib/i18n";
import { useMainButton } from "../lib/useMainButton";

/**
 * Post-registration "moment of pride" screen.
 *
 *   - Big greeting with the master's name + their public URL.
 *   - QR pointing at https://grancvi.am/{slug} — printable, shareable.
 *   - Copy-link / Share-to-Telegram buttons for instant distribution.
 *   - Three-bullet "what's next" mini-checklist (no progress tracking,
 *     just hints).
 *   - TG MainButton + inline button → /  (master dashboard).
 */
export function Welcome() {
  const { t } = useLang();
  const navigate = useNavigate();
  const me = useMe();
  const [copied, setCopied] = useState(false);

  const profile = me.data?.profile;
  const slug = profile?.slug ?? "";
  const url = slug ? `https://grancvi.am/${slug}` : "";

  function copy() {
    if (!url) return;
    navigator.clipboard.writeText(url).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      },
      () => {
        /* ignore */
      },
    );
  }

  function shareTelegram() {
    if (!url) return;
    const text = t("welcome_share_message");
    const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
    if (typeof window !== "undefined" && window.Telegram?.WebApp?.openTelegramLink) {
      window.Telegram.WebApp.openTelegramLink(shareUrl);
    } else {
      window.open(shareUrl, "_blank", "noopener");
    }
  }

  function goDashboard() {
    navigate("/", { replace: true });
  }

  useMainButton({
    text: t("welcome_to_dashboard"),
    enabled: true,
    visible: true,
    onClick: goDashboard,
  });

  if (me.isLoading || !profile) {
    return (
      <Layout title="">
        <div className="p-6 space-y-4">
          <div className="h-8 rounded-xl bg-white/40 dark:bg-white/10 animate-pulse" />
          <div className="h-48 rounded-xl bg-white/40 dark:bg-white/10 animate-pulse" />
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="">
      <div className="p-6 space-y-6">
        <div className="space-y-1 text-center">
          <h1 className="text-2xl font-bold">
            {t("welcome_title_fmt", { name: profile.master_name ?? profile.first_name })}
          </h1>
          <p className="text-sm text-tg-hint leading-relaxed">
            {t("welcome_subtitle")}
          </p>
        </div>

        <div className="flex flex-col items-center gap-3">
          <div className="bg-white p-4 rounded-2xl shadow-sm">
            <QRCodeSVG value={url} size={200} level="M" />
          </div>
          <div className="font-mono text-sm text-tg-text">{url}</div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={copy}
            className="rounded-xl bg-white/80 dark:bg-black/20 border border-black/5 dark:border-white/10 px-4 py-3 text-sm font-medium active:opacity-70"
          >
            {copied ? t("welcome_copy_done") : t("welcome_copy_link")}
          </button>
          <button
            type="button"
            onClick={shareTelegram}
            className="rounded-xl bg-tg-button text-tg-button-text px-4 py-3 text-sm font-semibold active:opacity-80"
          >
            {t("welcome_share_tg")}
          </button>
        </div>

        <div className="rounded-2xl bg-white/40 dark:bg-white/5 border border-black/5 dark:border-white/10 px-4 py-3 space-y-2">
          <h3 className="text-xs font-semibold text-tg-hint uppercase tracking-wide">
            {t("welcome_what_next")}
          </h3>
          <ul className="text-sm text-tg-text space-y-1.5">
            <li className="flex gap-2"><span>·</span><span>{t("welcome_tip_print")}</span></li>
            <li className="flex gap-2"><span>·</span><span>{t("welcome_tip_instagram")}</span></li>
            <li className="flex gap-2"><span>·</span><span>{t("welcome_tip_help")}</span></li>
          </ul>
        </div>

        {!isTMA() && (
          <button
            type="button"
            onClick={goDashboard}
            className="w-full rounded-xl bg-tg-button text-tg-button-text px-4 py-3 text-sm font-semibold active:opacity-80"
          >
            {t("welcome_to_dashboard")}
          </button>
        )}
      </div>
    </Layout>
  );
}
```

- [ ] **Step 2: Скомпилировать**

Run:
```bash
pnpm exec tsc -b --noEmit
```
Expected: clean. Если падает на `window.Telegram.WebApp.openTelegramLink` — проверить тип в `src/lib/telegram.ts` или `@twa-dev/sdk`. Можно ослабить через `(window as unknown as { Telegram?: { WebApp?: { openTelegramLink?: (s: string) => void } } })`.

- [ ] **Step 3: Коммит**

```bash
git add src/pages/Welcome.tsx
git commit -m "feat(welcome): post-register screen with QR + share buttons"
```

---

### Task 16: Подключить роут `/welcome` + soft-redirect `/onboarding` → `/`

**Files:**
- Modify: `src/App.tsx:17, 110-112, 137`

- [ ] **Step 1: Добавить импорт `Welcome`**

В `src/App.tsx:17` (рядом с `import { Onboarding }`):

```typescript
import { Onboarding } from "./pages/Onboarding";
import { Welcome } from "./pages/Welcome";
```

- [ ] **Step 2: Не редиректить master c `onboarded === false` в `/onboarding`**

Найти в `RoleRouter()` (около строки 110):

```typescript
  if (me.data?.role === "master") {
    if (me.data.onboarded === false) {
      return <Navigate to="/onboarding" replace />;
    }
    return <MasterDashboard name={me.data.profile.master_name ?? "Master"} />;
  }
```

Заменить на:

```typescript
  if (me.data?.role === "master") {
    // Onboarding wizard removed — registration form now does everything
    // in one shot. Backwards-compat: any in-flight master with
    // onboarded=false (legacy) lands on dashboard anyway; their default
    // hours are already populated and they can add services from there.
    return <MasterDashboard name={me.data.profile.master_name ?? "Master"} />;
  }
```

- [ ] **Step 3: Добавить `/welcome` роут и заменить `/onboarding` на soft-redirect**

В `<Routes>`-блоке (строки ~123-142) найти:

```tsx
        <Route path="/onboarding" element={<Onboarding />} />
```

Заменить на:

```tsx
        <Route path="/welcome" element={<Welcome />} />
        {/* Legacy: any in-flight tab with /onboarding open → safe redirect home. */}
        <Route path="/onboarding" element={<Navigate to="/" replace />} />
```

- [ ] **Step 4: Удалить неиспользуемый импорт `Onboarding`**

```typescript
import { Onboarding } from "./pages/Onboarding";
```
↑ строку убрать. Файл `src/pages/Onboarding.tsx` пока **оставляем** (удалим в следующем PR).

- [ ] **Step 5: Скомпилировать**

Run:
```bash
pnpm exec tsc -b --noEmit
```
Expected: clean.

- [ ] **Step 6: Коммит**

```bash
git add src/App.tsx
git commit -m "feat(routes): wire /welcome, redirect /onboarding → /, drop master-onboarded gate"
```

---

### Task 17: Локальный smoke-тест полного флоу

**Files:** N/A

- [ ] **Step 1: Поднять backend локально (если не запущен)**

В `tg-bot/`:
```bash
cd /Users/vanik/Desktop/projects/working-projects/tg-bot
git checkout feat/onboarding-redesign-backend  # из Phase 1
docker compose up -d postgres redis
uv run uvicorn src.api.main:app --reload --port 8000
```

- [ ] **Step 2: Поднять фронт**

В `grancvi-web/`:
```bash
cd /Users/vanik/Desktop/projects/working-projects/grancvi-web
pnpm dev
```

- [ ] **Step 3: Открыть `http://localhost:5173/register/self?startParam=signup`**

В Chrome DevTools:
- Очистить localStorage и sessionStorage
- Открыть как обычный браузер (без Telegram WebApp обвязки)

Expected:
- Заголовок «Վարպետի գրանցում» (армянский по дефолту)
- Поля «Имя» / «Ссылка» / «Чем занимаешься?»

- [ ] **Step 4: Заполнить форму и засабмитить**

1. Имя: `Test Master`
2. Slug: автогенерится — оставить или поменять
3. Кликнуть 1-2 чипа специализации (например «Парикмахер ж.» + «Колорист»)
4. Услуги — все по дефолту выбраны
5. Нажать кнопку «Готов начинать · {N} услуг»

Expected:
- POST `/v1/register/master/self` → 201
- Серия POST `/v1/master/services` → 201 каждый
- POST `/v1/me/onboarded` → 200 (или 4xx если уже)
- Редирект на `/welcome`
- Welcome-экран с QR-кодом, ссылкой `grancvi.am/<slug>`, кнопками Copy / Share

- [ ] **Step 5: Проверить что `/onboarding` редиректит на `/`**

Открыть `http://localhost:5173/onboarding` напрямую → должен редиректнуть на `/`.

- [ ] **Step 6: Проверить рестарт сценария — пользователь уже зарегистрирован**

Перезагрузить `http://localhost:5173/register/self?startParam=signup` тем же tg_id → expected 409 `already_registered`. Ошибка должна показаться юзеру через `errorMessage(register.error, t)`.

- [ ] **Step 7: Проверить дефолт языка**

Снова очистить localStorage. Открыть `http://localhost:5173/`. Expected — UI на армянском.

- [ ] **Step 8: Если все 7 шагов прошли — продолжаем. Если нет — починить, перезапустить smoke-тест.**

---

### Task 18: Финальная проверка фазы 2 + push

- [ ] **Step 1: Билд продакшна**

Run:
```bash
pnpm build
```
Expected: clean, нет ошибок tsc / vite.

- [ ] **Step 2: Линт**

```bash
pnpm exec eslint src --max-warnings 0
```
Expected: clean. Если есть warnings про unused vars (`Onboarding` import, etc) — починить.

- [ ] **Step 3: Запушить ветку**

```bash
git push -u origin feat/onboarding-redesign
```

- [ ] **Step 4: Сообщить пользователю**

«Фронт-ветка `feat/onboarding-redesign` (в `grancvi-web/`) готова. Бэк-ветка готова отдельно. Готов координировать деплой бэка → фронта.»

---

## Phase 3 — Деплой и верификация на проде

### Task 19: Деплой бэка

**Pre-deploy:**

- [ ] **Step 1: Подтвердить от пользователя что катим**

Спросить: «Готов запустить деплой backend (`tg-bot`) на прод? Это безвредно для текущих пользователей — старый фронт продолжает работать. Yes/no.»

Если no — стоп, ждём.

- [ ] **Step 2: Мердж в main**

```bash
cd /Users/vanik/Desktop/projects/working-projects/tg-bot
git checkout main && git pull
git merge --no-ff feat/onboarding-redesign-backend -m "Merge: onboarding redesign — backend"
git push origin main
```

- [ ] **Step 3: Деплой**

(Допустим деплой триггерится через push в main — если нет, выполнить руками тот же флоу что и для предыдущих эпиков.)

- [ ] **Step 4: После деплоя — sanity-check**

```bash
curl -sf https://api.grancvi.am/v1/health   # подставить реальный URL если другой
```
Expected: 200.

- [ ] **Step 5: Проверить что в логах нет регрессий 5 минут**

(SSH на прод, `docker compose logs --tail 200 -f api app_bot`.) Expected: нормальные логи, никаких трейсбеков.

- [ ] **Step 6: Тестовая регистрация через текущий (пока не задеплоенный) фронт**

Открыть прод-фронт `https://app.grancvi.am`. Зарегистрироваться. Expected: всё работает как раньше — пользователь регистрируется, попадает в чек-лист онбординга, может выбрать услуги. **Это критично — иначе бэк сломал старый фронт.**

---

### Task 20: Деплой фронта

**Pre-deploy:**

- [ ] **Step 1: Подтвердить от пользователя**

Спросить: «Бэк выкатился, регресс не наблюдается. Запустить деплой фронта?»

Если no — стоп, бэк может пожить с обратной совместимостью.

- [ ] **Step 2: Мердж в main `grancvi-web`**

```bash
cd /Users/vanik/Desktop/projects/working-projects/grancvi-web
git checkout main && git pull
git merge --no-ff feat/onboarding-redesign -m "Merge: onboarding redesign — frontend"
git push origin main
```

- [ ] **Step 3: Триггернуть деплой `grancvi-web`**

(Допустим Vercel/Cloudflare Pages автодеплоит из main — иначе запустить руками.)

- [ ] **Step 4: Дождаться завершения и проверить**

Открыть `https://app.grancvi.am/register/self?startParam=signup`. Expected: новый дизайн, армянский по дефолту, всё работает end-to-end.

---

### Task 21: Полный E2E прод-смоук

- [ ] **Step 1: Сделать тестовую регистрацию мастером с лендинга**

Зайти на `https://grancvi.am`, нажать CTA «Стать мастером» (← после деплоя — должна быть «Դառնալ վարպետ» на армянском), пройти весь флоу.

Expected:
- Бот: «Վարպետի գրանցում՝ մի քանի թափով.» + кнопка «Դառնալ վարպետ»
- TMA: новый одно-экранный RegisterSelf
- После сабмита: Welcome с QR
- QR на телефоне сосканировать → открывается `grancvi.am/<slug>` → открывается публичная страница (НЕ 404)
- Запись через клиента работает

- [ ] **Step 2: Проверить admin-уведомление**

В личке у админа (`admin_tg_ids`): «🆕 Новый мастер 👤 ... Если что-то не то — /block <slug>».

- [ ] **Step 3: Проверить что reserved-slug отказывает**

Попытаться зарегистрироваться с slug `admin`. Expected: ошибка «slug_reserved» с понятным сообщением в форме.

- [ ] **Step 4: Удалить тестовую регистрацию**

Через админку или прямой DB-запрос:
```sql
DELETE FROM appointments WHERE master_id = (SELECT id FROM masters WHERE slug = '<test-slug>');
DELETE FROM services WHERE master_id = (SELECT id FROM masters WHERE slug = '<test-slug>');
DELETE FROM masters WHERE slug = '<test-slug>';
```

- [ ] **Step 5: Финальный коммит CHANGELOG**

(Если в репо есть `CHANGELOG.md` — обновить.) Пример:

```markdown
## [Unreleased]
### Changed
- Регистрация мастера теперь один экран: имя + slug + специализации + услуги (предвыбраны).
- Welcome-страница после регистрации с QR и share-кнопками.
- Self-service регистрация больше не на модерации — мастер сразу public.
- Reserved-slug список расширен популярными именами.
- Дефолт языка — армянский.
- Контекстный копирайт лаунчер-кнопки в боте под start_param.
```

- [ ] **Step 6: Сообщить пользователю что всё на проде, доступно тестировать**

«Готово. Прод обновлён. Зарегистрируйся ещё раз сам и пощёлкай — обратная связь приветствуется. Если что-то горит — `git revert -m 1 <merge-sha>` в обоих репо и redeploy.»

---

## Self-Review

После написания плана проверил против спека:

**Spec coverage:**
- [x] Один экран регистрации → Task 14
- [x] Welcome-экран с QR → Task 15
- [x] `is_public=true` для мастера → Task 4
- [x] `is_public=true` для салона → Task 5
- [x] Reserved-slug list → Task 2
- [x] Reserved-slug → 409 в API → Task 3
- [x] `_inline_label_for(payload, lang)` контекстный → Task 7
- [x] Welcome-text per start_param → Task 7
- [x] Дефолт армянский в боте → Task 7
- [x] Дефолт армянский в TMA → Task 11
- [x] Удалить чек-лист `Onboarding` → Task 16 (route → redirect; файл оставляем)
- [x] Координация деплоя бэк→фронт → Task 19, 20
- [x] Admin notification copy update → Task 6
- [x] `onboarded_at` авто-выставляется → Task 4

**Placeholder scan:** Прошёлся по плану, нет «TBD»/«TODO» в шагах. Все code-блоки полные. `RESERVED_SLUGS` в Task 2 — финальный список (illustrative seed из спека уже расширен до фактически коммитимого).

**Type consistency:**
- `register.mutateAsync({...})` сигнатура совпадает с существующей `useRegisterMasterSelf` (см. `RegisterSelf.tsx` оригинал)
- `createService.mutateAsync({name, duration_min, price_amd, preset_code})` — то же что в `MasterServices.tsx` `PresetPicker` сейчас
- `_inline_label_for` всегда `(start_param, lang) → str` — единая сигнатура везде в Task 7

**Open questions for user before exec:**
- В Task 7 я предполагаю что в `app_bot/handlers.py` доступна `AsyncSession` через middleware — если нет, нужно подключить через `bot.dispatcher` setup (это типичный паттерн, но проверить).
- Финальный список `RESERVED_SLUGS` — содержание утверждаю с пользователем перед мерджем (см. Task 2 step 3).
