# Epic 9: Multi-Master v1 — Design

**Дата:** 2026-04-22
**Статус:** Design approved, ready for plan
**Предшествующий эпик:** 8.2 (Docker prod deploy) — закрыт, тег `v0.8.2-epic-8-2-deploy` → `6f1f2fc`

---

## 1. Цель

Превратить single-tenant бота (1 мастер = 1 инстанс) в shared-instance multi-master платформу: один бот `@grancvi_bot` обслуживает **несколько мастеров одновременно**, у каждого — свой слаг, своя публичная витрина, свои клиенты и расписание. Клиенты записываются через персональные deep-link'и мастера, либо через общий каталог.

**Бизнес-повод:** пользователь хочет дать доступ другу-стоматологу для теста, не разворачивая второй инстанс. Параллельно решаются проблемы BotFather-лимита (20 ботов на аккаунт), фрагментации инфры и аналитики.

---

## 2. Роли и смешивание

Три роли на уровне кода:

| Роль | Как становится | Команды/кнопки |
|------|----------------|----------------|
| **Admin** | Telegram ID в `ADMIN_TG_IDS` (env) | Все админские + мастерские + клиентские |
| **Master** | Зарегистрировался по инвайт-ссылке | Мастерские + клиентские |
| **Client** | Просто написал боту (или кликнул `/start master_<slug>`) | Клиентские |

**Смешивание разрешено:**
- Admin всегда имеет доступ к админке + к своему мастерскому кабинету (если зарегистрировался как мастер).
- Master может быть клиентом у другого мастера (например, стоматолог записывается к своему парикмахеру через того же бота). Для этого один `tg_id` может иметь несколько записей `clients` с разными `master_id`.
- Admin-статус определяется ТОЛЬКО по env, **не** хранится в БД. Это защищает от случайной потери доступа при миграциях.

---

## 3. Модель данных

### 3.1 Изменения в существующей таблице `masters`

```sql
ALTER TABLE masters
  ADD COLUMN slug VARCHAR(32) UNIQUE NOT NULL,  -- латиница+цифры+дефис, 3-32 символа
  ADD COLUMN specialty_text VARCHAR(200) NOT NULL DEFAULT '',  -- свободный ввод мастера
  ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT TRUE,  -- показывать в общем каталоге
  ADD COLUMN blocked_at TIMESTAMPTZ NULL;  -- NULL = активен; timestamp = заблокирован
```

**Индексы:**
- `CREATE UNIQUE INDEX ix_masters_slug ON masters(slug);`
- `CREATE INDEX ix_masters_catalog ON masters(is_public, blocked_at) WHERE blocked_at IS NULL AND is_public = TRUE;` — для каталога.

**Правила слага:**
- Формат: `^[a-z0-9-]{3,32}$`, не начинается и не заканчивается на `-`, нет `--`.
- Зарезервированные префиксы нельзя: `admin`, `bot`, `api`, `grancvi`, `master`, `client`, `invite`.
- Генерация по умолчанию: транслит `first_name` (Анна → `anna`) + 4 hex-символа (`anna-7f3c`). Если транслит пуст — `master-XXXX`.
- Мастер может **один раз** сменить слаг в настройках после регистрации (чтобы не ломать старые ссылки; редкое изменение — ок, но поток регистрации не должен требовать «подобрать идеальный» заранее).

### 3.2 Новая таблица `invites`

```sql
CREATE TABLE invites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code VARCHAR(16) NOT NULL UNIQUE,  -- формат: A7K2-X9MP
  created_by_tg_id BIGINT NOT NULL,  -- admin или master, кто выдал
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,  -- created_at + 7 дней
  used_by_tg_id BIGINT NULL,  -- NULL = не использован
  used_at TIMESTAMPTZ NULL,
  used_for_master_id UUID NULL REFERENCES masters(id) ON DELETE SET NULL
);

CREATE INDEX ix_invites_code ON invites(code);
CREATE INDEX ix_invites_creator ON invites(created_by_tg_id, created_at DESC);
```

**Инвариант:** `(used_by_tg_id IS NULL) = (used_at IS NULL) = (used_for_master_id IS NULL)`. Либо всё NULL (не использован), либо всё заполнено.

**Формат кода:** `XXXX-XXXX` из `A-Z` (без `I`, `O`) и `0-9` (без `0`, `1`) → 32 символа алфавита × 8 позиций ≈ 10¹² вариантов. Одноразовый, срок жизни 7 дней, deep-link-совместимый.

### 3.3 Удаляется

— пока ничего. Старая таблица `clients(tg_id, master_id, …)` остаётся как есть: `(tg_id, master_id)` уже уникально — это поддерживает случай «один tg_id = клиент у нескольких мастеров».

---

## 4. Ключевые потоки

### 4.1 Регистрация мастера по инвайту

**Выдача инвайта:**
- Admin или другой master нажимает `➕ Пригласить мастера` (в settings submenu → см. §6).
- Система создаёт `invites` запись, возвращает сообщение:
  > Код инвайта: `A7K2-X9MP` (действителен 7 дней)
  > Ссылка: https://t.me/grancvi_bot?start=invite_A7K2-X9MP
- Master пересылает ссылку другу.

**Активация:**
- Друг кликает ссылку → `/start invite_A7K2-X9MP` → handler парсит payload.
- Проверки: код существует, не использован, не просрочен.
- Если tg_id уже мастер — отвечаем «Вы уже зарегистрированы» и не трогаем инвайт.
- Иначе стартует FSM `MasterRegistration`:
  1. Приветствие + спросить имя (или взять из `from_user.first_name` с кнопкой «Использовать Анна»).
  2. Спросить специальность: reply-keyboard с кнопками-подсказками (`💈 Парикмахер`, `🦷 Стоматолог`, `💅 Мастер маникюра`, `💆 Косметолог`, `✏️ Своё`). Кнопка вставляет текст, можно отредактировать перед отправкой; «Своё» = пустой ввод.
  3. Предложить автоген-слаг (`anna-7f3c`) с двумя кнопками: `✅ Использовать` / `✏️ Изменить`. Если `✏️` — приём ввода с валидацией (regex + занятость + reserved).
  4. Создать `masters` запись, пометить инвайт как использованный, показать главное меню.

### 4.2 Клиент по deep-link мастера

- Клиент кликает `https://t.me/grancvi_bot?start=master_anna-7f3c`.
- Handler `/start` с payload `master_<slug>`:
  1. Найти мастера по slug.
  2. Если не найден / заблокирован / `is_public=false` — показать «Мастер не найден» + кнопку `📋 Посмотреть всех мастеров` (каталог).
  3. Иначе — сохранить `master_id` в FSM (`BookingFlow.master_id`), показать карточку мастера (имя, специальность, «📅 Записаться» inline-кнопка), и далее стандартный booking flow.

### 4.3 Общий каталог (fallback для `/start` без payload)

- Клиент пишет `/start` без payload → если у него нет активной записи/мастера в контексте, показать каталог.
- Каталог: inline-карточки всех `is_public=true AND blocked_at IS NULL`, отсортированные по `created_at ASC` (первые зарегистрированные — первые в списке). Пагинация не нужна для v1 (реалистично <20 мастеров).
- Каждая карточка: `👤 Анна — 🦷 Стоматолог` + inline-кнопка `📅 Записаться` → ведёт в тот же booking flow.

### 4.4 Soft block (админ блокирует мастера)

Админ делает `/block anna-7f3c` (или через админ-меню):
1. `masters.blocked_at = NOW()`.
2. Все `appointments WHERE master_id = X AND status = 'pending'` → `status = 'rejected'`, `reject_reason = 'master_blocked'`.
3. Клиентам с rejected pending — уведомление «К сожалению, мастер временно недоступен».
4. `appointments.status = 'confirmed'` **не трогаем** (клиенты ждут, мастер сам разрулит при разблокировке).
5. Мастер при заходе в бота видит баннер «⛔ Ваш кабинет временно заблокирован администратором». Новые кнопки/команды мастерских действий отклоняются с тем же сообщением (кроме `/start` и settings-просмотра).

Unblock (`/unblock anna-7f3c`) просто `blocked_at = NULL`. Отказанные бронирования не восстанавливаются.

---

## 5. Слои кода

### 5.1 Repositories

- `MasterRepo.by_slug(slug) -> Master | None`
- `MasterRepo.list_public() -> list[Master]` (для каталога)
- `MasterRepo.create(tg_id, name, specialty_text, slug) -> Master`
- `MasterRepo.update_slug(master_id, new_slug)` (атомарно, ловит IntegrityError → `SlugTaken`)
- `MasterRepo.set_blocked(master_id, blocked: bool)`
- `InviteRepo.create(created_by_tg_id) -> Invite`
- `InviteRepo.by_code(code) -> Invite | None`
- `InviteRepo.mark_used(code, used_by_tg_id, master_id)`
- `InviteRepo.list_by_creator(tg_id) -> list[Invite]` (для `/myinvites`)

### 5.2 Services

- `InviteService.generate_code() -> str` (чистая функция, отдельно тестируется)
- `InviteService.create_invite(actor_tg_id: int, is_admin: bool) -> Invite` — единственная точка создания. (В v1 без rate-limit, но сервис — место, где он появится.)
- `InviteService.redeem(code: str, tg_id: int) -> Invite` — проверки + пометка. Возвращает обновлённый инвайт или кидает `InviteNotFound` / `InviteExpired` / `InviteAlreadyUsed`.
- `SlugService.generate_default(first_name: str) -> str` — транслит + суффикс, гарантирует доступность через retry-loop (до 5 попыток, потом `master-XXXX`).
- `SlugService.validate(slug: str) -> None` — regex + reserved, кидает `InvalidSlug` / `ReservedSlug`.
- `MasterRegistrationService.register(tg_id, name, specialty, slug, invite_code) -> Master` — транзакционно создаёт мастера + помечает инвайт.
- `ModerationService.block_master(slug: str) -> int` — блокирует + возвращает число отменённых pending'ов. Отправкой уведомлений клиентам занимается handler (ему доступен `bot`), сервис возвращает список `appointment_id + client_tg_id` для рассылки.

### 5.3 Handlers

Файловая структура:
```
src/handlers/
  admin/
    __init__.py     # router
    menu.py         # reply-keyboard admin_menu dispatch
    masters.py      # /masters, /master <slug>, /stats
    invites.py      # /invites
    moderation.py   # /block, /unblock
  master/
    menu.py         # (уже есть) + добавить handle_my_link, handle_my_invites, handle_invite_master
    registration.py # FSM MasterRegistration (invite redeem flow)
    settings.py     # (уже есть) + подраздел «Мой профиль» + подраздел «Инвайты»
  client/
    start.py        # /start, /start invite_<code>, /start master_<slug>
    catalog.py      # handle_catalog_button, render_catalog_card
```

### 5.4 FSM

- `MasterRegistration` — NEW: states `waiting_name`, `waiting_specialty`, `waiting_slug_confirm`, `waiting_custom_slug`.
- `AdminNewInvite` — не нужна (одна кнопка → один ответ).
- Существующие FSM (`BookingFlow`, `ManualAppointment`, …) получают обязательный `master_id` в `state.data` — это уже так для мастерских FSM, нужно проверить клиентский `BookingFlow` и явно класть туда `master_id` при старте.

### 5.5 Middlewares

**`UserMiddleware` (src/middlewares/user.py:43) — критичный фикс:**

Сейчас делает `session.scalar()` для поиска клиента по `tg_id` — при multi-master это упадёт с `MultipleResultsFound`, как только один tg_id запишется к двум мастерам.

**Решение:** UserMiddleware НЕ ищет клиента в БД. Он только:
- определяет, admin ли это (по env),
- если tg_id есть в `masters` — подкладывает `master` в data,
- `client` НЕ подкладывает вообще.

Клиентская запись ищется на уровне сервиса `BookingService` по паре `(tg_id, master_id)`, где `master_id` пришёл из FSM или из deep-link payload.

**`LangMiddleware` и `DbSessionMiddleware`** — без изменений.

---

## 6. Кнопки и команды (по `feedback_ux_buttons.md`)

Все новые команды обязаны иметь кнопочный путь. Слеш-команды — только для Menu-button списка.

### 6.1 Master

**`main_menu()` reply-keyboard** (src/keyboards/common.py) — добавить кнопку:
- `🔗 Моя ссылка` — рядом с `🔎 Поиск клиента` или в отдельном ряду.

Итоговый master main_menu (8 кнопок, 4 ряда):
```
[📅 Сегодня]    [📋 Завтра]
[🗓 Неделя]     [📆 Календарь]
[➕ Добавить]  [🔎 Поиск клиента]
[🔗 Моя ссылка] [⚙️ Настройки]
```

**`settings_menu()` inline-keyboard** (src/keyboards/common.py или src/keyboards/settings.py) — добавить:
- `👤 Мой профиль` (редактор имени / специальности / слага)
- `📨 Мои инвайты` → список выданных + статус
- `➕ Пригласить мастера` → создать новый инвайт

**Slash-команды (Menu button, MASTER scope):**
- `/mylink` → то же, что `🔗 Моя ссылка`
- `/myinvites` → то же, что `📨 Мои инвайты`
- `/new_invite` → то же, что `➕ Пригласить мастера`
- (+ существующие: start, today, tomorrow, week, calendar, add, client, services, cancel)

### 6.2 Admin

**Новая `admin_menu()` reply-keyboard** (src/keyboards/admin.py — NEW):
```
[👥 Мастера]    [📊 Статистика]
[📨 Инвайты]    [🛠 Модерация]
[⬅️ В главное меню]
```

- `👥 Мастера` → список всех мастеров (id, slug, имя, специальность, статус, дата регистрации), inline-кнопки `Заблокировать/Разблокировать` для каждого.
- `📊 Статистика` → агрегат: кол-во мастеров (active/blocked), кол-во клиентов (distinct tg_id), кол-во appointments за 7/30 дней.
- `📨 Инвайты` → список всех инвайтов (код, кем выдан, срок, использован/нет).
- `🛠 Модерация` → список мастеров с быстрыми кнопками блокировки.

Admin main_menu (reply):
- Если admin **также зарегистрирован как мастер** (типичный кейс — это я) — на `/start` показываем `main_menu()` (мастерские кнопки), а в `settings_menu()` добавляем inline-кнопку `🛠 Админ` для вызова `admin_menu()`.
- Если admin **не является мастером** (друг-тестировщик с ADMIN_TG_IDS) — на `/start` сразу показываем `admin_menu()` как основное меню.
- Определяется в `/start` handler'е по наличию `master` в data от `UserMiddleware`.

**Slash-команды (Menu button, ADMIN scope):**
- `/masters`
- `/master <slug>`
- `/stats`
- `/invites`
- `/block <slug>`
- `/unblock <slug>`

### 6.3 Client

- `/start` без payload → каталог (см. §4.3) с inline-кнопками мастеров.
- `/start master_<slug>` → карточка мастера + `📅 Записаться`.
- `/start invite_<code>` → если tg_id не мастер, регистрация; иначе — «Вы уже мастер».
- После успешного бронирования — `ReplyKeyboardRemove()` (у клиента не должно оставаться мастерской клавиатуры на экране).

---

## 7. Миграции и обратная совместимость

### 7.1 Alembic revision

```
alembic revision -m "epic-9: multi-master — slug, specialty, is_public, blocked_at + invites table"
```

**Upgrade:**
1. Создать таблицу `invites`.
2. `ALTER TABLE masters ADD COLUMN slug VARCHAR(32) NULL` (пока NULL allowed).
3. `ALTER TABLE masters ADD COLUMN specialty_text VARCHAR(200) NOT NULL DEFAULT ''`.
4. `ALTER TABLE masters ADD COLUMN is_public BOOLEAN NOT NULL DEFAULT TRUE`.
5. `ALTER TABLE masters ADD COLUMN blocked_at TIMESTAMPTZ NULL`.
6. **Data migration:** для каждой существующей `masters` записи сгенерировать slug через `SlugService.generate_default(first_name)` и записать.
7. `ALTER TABLE masters ALTER COLUMN slug SET NOT NULL`.
8. Добавить unique index на slug.

**Downgrade:** drop колонок + drop таблицы invites.

### 7.2 Обратная совместимость

- Существующий единственный мастер (пользователь) получает авто-сгенерированный slug. В settings он сможет поменять.
- Клиенты, у которых FSM завис на старой схеме без `master_id` — state сбрасывается при первом `/start` (уже так работает).
- `ADMIN_TG_IDS` env-переменная — уже существует (используется в `setup_bot_commands`). Без изменений.

---

## 8. Out of scope для v1

Явно не делаем в этом эпике:
- ❌ Hard-delete мастера (только soft block).
- ❌ Rating/reviews клиентами.
- ❌ Фото мастера / портфолио.
- ❌ Категории-фильтры в каталоге («показать только стоматологов»).
- ❌ Rate-limit на создание инвайтов (1 мастер = сколько угодно инвайтов).
- ❌ Реферальная программа для клиентов.
- ❌ `/myappointments` для клиентов (пусть пока через уведомления).
- ❌ Платежи / подписки для мастеров.
- ❌ Мульти-локационные мастера (1 мастер = 1 локация).

Эти пункты попадут в отдельные эпики, если продукт пойдёт.

---

## 9. Риски и mitigations

| Риск | Вероятность | Импакт | Mitigation |
|------|-------------|--------|------------|
| Конфликт FSM между мастером и клиентом для одного tg_id | Средняя | Высокий | FSM-state хранит `mode: master\|client` + `master_id`; при смене mode — `state.clear()` |
| Slug-генератор зацикливается при высокой конкуренции | Низкая | Средний | До 5 попыток с random suffix, потом fallback `master-<6hex>` |
| Утечка invite-кодов (друг переслал в публичный чат) | Средняя | Низкий | Одноразовый + 7-дневный TTL; админ видит в `/invites` кто использовал |
| Забанен один из админов Telegram'ом | Низкая | Высокий | `ADMIN_TG_IDS` — список, не один ID |
| Data migration slug генерирует коллизию | Низкая | Средний | Миграция с retry-loop, fail-loud при невозможности |
| Клиент записан к заблокированному мастеру (confirmed) и мастер «пропал» | Средняя | Средний | Клиенту уведомление не отправляем; при unblock всё восстанавливается |

---

## 10. Acceptance Criteria

1. ✅ Admin может создать инвайт (`/new_invite` или `➕ Пригласить мастера` в settings) и получает код + deep-link.
2. ✅ Новый tg_id по deep-link `/start invite_<code>` проходит FSM регистрации и становится мастером.
3. ✅ После регистрации у нового мастера свой slug, своя клавиатура `main_menu()`, свой пустой календарь.
4. ✅ Клиент по ссылке `t.me/grancvi_bot?start=master_<slug>` попадает в booking flow конкретного мастера.
5. ✅ Клиент без payload (`/start`) видит каталог всех `is_public=true, blocked_at IS NULL` мастеров.
6. ✅ Один tg_id может быть клиентом у двух разных мастеров без краша (`UserMiddleware` не падает на `MultipleResultsFound`).
7. ✅ Admin может `/block <slug>` — мастерские pending автоматически rejected, мастер видит баннер блокировки при любом действии.
8. ✅ Admin может `/unblock <slug>` — мастер снова работает, отказанные бронирования НЕ восстанавливаются.
9. ✅ `/masters`, `/stats`, `/invites` возвращают корректные данные (проверяется в тестах).
10. ✅ Slash-команды зарегистрированы в `setup_bot_commands()` по scope (admin / master / client).
11. ✅ Каждая новая команда имеет кнопочный путь (тесты `test_handlers_*_menu_dispatch.py`).
12. ✅ Data migration: существующий мастер после `alembic upgrade head` имеет валидный slug.
13. ✅ mypy --strict + ruff + все тесты зелёные.

---

## 11. Реалистичный timeline

**НЕ 1 день.** Пользователь оценил в 1 день — на самом деле это ~2-3 дня фокусной работы с TDD и subagent-driven review.

Ориентировочная декомпозиция (дет. план — в `2026-04-22-epic-9-multi-master.md`):

| Задача | Прикид |
|--------|--------|
| Миграция + модели + repo для masters/invites | 3h |
| SlugService + InviteService (чистые тесты) | 2h |
| MasterRegistration FSM | 3h |
| Client deep-link + каталог | 3h |
| Admin menu + команды + handlers | 4h |
| UserMiddleware рефакторинг + фикс клиентского поиска | 2h |
| Кнопки (main_menu/settings/admin) + тесты диспатча | 2h |
| setup_bot_commands по scope | 1h |
| Block/unblock flow + уведомления клиентам | 3h |
| E2E smoke + багфиксы | 3h |

**Итого:** ~26h = 2-3 рабочих дня при полной загрузке.

---

**Конец design-спеки Эпика 9.**
