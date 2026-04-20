# Botik — Telegram-бот для записи к стоматологу/парикмахеру/итд

## Общая идея

Telegram-бот, заменяющий блокнот и звонки для small business в сфере приёмов (стоматолог, парикмахер, барбер, мастер маникюра, косметолог). Рынок — Армения.

Два типа пользователей:

- **Мастер (врач)** — ведёт приём, управляет расписанием через бота.
- **Клиент** — записывается к конкретному мастеру через ссылку на бота.

## Ключевые принципы продукта

1. **Request-to-book, не instant-book.** Клиент присылает заявку → мастер подтверждает. Причина: мастер часто знает про занятость то, чего бот не знает (клиент позвонил устно, затянулся приём, заболел врач).
2. **Мастер главнее бота.** Мастер может добавлять, переносить, отменять записи вручную — без промежуточных подтверждений.
3. **Простота.** Каждый экран — максимум 2–5 кнопок. Никаких многоуровневых меню.
4. **Solo-мастер.** На старте бот обслуживает одного мастера. Multi-tenant архитектура заложена с первого дня, но UX мульти-мастера в одной клинике — отложен.
5. **Telegram-напоминания, не СМС.** СМС добавим позже; на MVP — только Telegram.

## Целевая аудитория первой версии

Индивидуальный стоматолог или парикмахер в Ереване, который:

- Ведёт приём один (или в кабинете, где каждый мастер сам себе хозяин).
- Ведёт записи в блокноте или заметках телефона.
- Теряет клиентов из-за no-show и путаницы.
- Готов платить ~5000 драм/мес за удобство.

---

## Технологический стек

| Компонент       | Выбор                       | Обоснование                                      |
| --------------- | --------------------------- | ------------------------------------------------ |
| Язык            | Python 3.12                 | Богатая экосистема для Telegram-ботов            |
| Фреймворк бота  | **aiogram 3.x**             | Современный, async, type-safe, FSM из коробки    |
| БД              | PostgreSQL 16               | JSON-поля, надёжная работа с tz, индексы с WHERE |
| ORM             | SQLAlchemy 2.0 (async)      | Индустриальный стандарт, async-поддержка         |
| Миграции        | Alembic                     | Стандарт для SQLAlchemy                          |
| Кэш/FSM-storage | Redis 7                     | FSM-хранилище aiogram, APScheduler jobstore      |
| Планировщик     | APScheduler 3.x             | Отложенные напоминания, тайм-ауты заявок         |
| Конфиг          | pydantic-settings           | Типизированные настройки из .env                 |
| Логи            | structlog                   | JSON-логи с контекстом                           |
| i18n            | aiogram_i18n + Fluent       | Армянский + русский                              |
| Тесты           | pytest + pytest-asyncio     | Стандарт                                         |
| Линтеры         | ruff + mypy (strict)        | Качество кода                                    |
| Контейнеризация | Docker + docker-compose     | Локально и на проде одинаково                    |
| Деплой          | Hetzner Cloud CX22 (€4/мес) | Простой VPS, Docker Compose                      |
| Reverse proxy   | Caddy                       | Автоматический HTTPS (для будущего webhook)      |
| CI              | GitHub Actions              | Lint + тесты + авто-деплой в main                |

---

## Структура проекта

```
botik/
├── docker-compose.yml         # postgres + redis + app
├── docker-compose.prod.yml    # прод-оверрайды
├── Dockerfile
├── pyproject.toml             # зависимости + ruff + mypy + pytest конфиг
├── alembic.ini
├── .env.example
├── .github/workflows/ci.yml
├── README.md
├── CLAUDE.md                  # правила для Claude Code
├── SPEC.md                    # этот документ
├── migrations/
│   └── versions/
├── tests/
│   ├── conftest.py
│   ├── test_availability.py   # чистая функция, покрыта полностью
│   ├── test_booking_flow.py
│   └── test_reminders.py
└── src/
    ├── main.py                # точка входа
    ├── config.py              # pydantic Settings
    ├── db/
    │   ├── base.py            # engine, session factory, Base
    │   └── models.py          # SQLAlchemy модели
    ├── repositories/          # CRUD + доменные запросы
    │   ├── masters.py
    │   ├── clients.py
    │   ├── appointments.py
    │   └── services.py
    ├── services/              # бизнес-логика (use-cases)
    │   ├── booking.py         # создание, подтверждение, отмена
    │   ├── availability.py    # расчёт свободных слотов (чистая функция)
    │   ├── reminders.py       # планирование напоминаний
    │   └── timeouts.py        # авто-отмена просроченных pending
    ├── handlers/
    │   ├── client/
    │   │   ├── start.py
    │   │   ├── booking.py     # FSM записи
    │   │   ├── my_bookings.py
    │   │   └── reminders_reply.py  # ответы на напоминания
    │   └── master/
    │       ├── start.py
    │       ├── today.py
    │       ├── week.py
    │       ├── calendar.py
    │       ├── add_manual.py  # FSM ручного добавления
    │       ├── approve.py     # callback'и подтверждения/отклонения
    │       ├── client_history.py
    │       └── settings.py
    ├── keyboards/
    │   ├── calendar.py        # кастомный inline-календарь
    │   ├── slots.py           # сетка времени (3 в ряд)
    │   ├── services.py
    │   └── common.py          # "Назад", "Отмена"
    ├── fsm/
    │   ├── client_booking.py
    │   └── master_add.py
    ├── callback_data/         # typed callback data
    │   ├── booking.py
    │   ├── calendar.py
    │   └── approval.py
    ├── middlewares/
    │   ├── db.py              # inject session в handler
    │   ├── user.py            # resolve master/client из tg_id
    │   └── i18n.py
    ├── locales/
    │   ├── ru/LC_MESSAGES/bot.ftl
    │   └── hy/LC_MESSAGES/bot.ftl
    ├── scheduler/
    │   ├── setup.py           # APScheduler init с Redis jobstore
    │   └── jobs.py            # определения job-функций
    └── utils/
        ├── time.py            # работа с Asia/Yerevan ↔ UTC
        ├── phone.py           # нормализация армянских номеров (+374)
        └── format.py          # форматирование сообщений бота
```

---

## Схема БД

Важные моменты:

- **Все `timestamptz` в БД хранятся в UTC.** Конвертация в `Asia/Yerevan` только на входе/выходе.
- **Unique partial index `(master_id, start_at) WHERE status IN ('pending', 'confirmed')`** — защита от race condition на бронировании.
- **Индекс на `(send_at) WHERE sent = false`** — планировщик быстро находит ближайшие напоминания.

### Таблицы

```sql
CREATE TABLE masters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tg_id BIGINT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    phone TEXT,
    timezone TEXT NOT NULL DEFAULT 'Asia/Yerevan',
    work_hours JSONB NOT NULL DEFAULT '{}',  -- {"mon": [["10:00","19:00"]], ...}
    breaks JSONB NOT NULL DEFAULT '{}',       -- обед: аналогичная структура
    slot_step_min INT NOT NULL DEFAULT 20,
    auto_confirm BOOLEAN NOT NULL DEFAULT FALSE,
    lang TEXT NOT NULL DEFAULT 'ru',          -- 'ru' | 'hy'
    decision_timeout_min INT NOT NULL DEFAULT 120,  -- сколько ждать ответа мастера
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    master_id UUID NOT NULL REFERENCES masters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    duration_min INT NOT NULL CHECK (duration_min > 0),
    price_amd INT,                             -- nullable, на MVP не используется
    active BOOLEAN NOT NULL DEFAULT TRUE,
    position INT NOT NULL DEFAULT 0,           -- для порядка отображения
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON services (master_id) WHERE active = TRUE;

CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    master_id UUID NOT NULL REFERENCES masters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    tg_id BIGINT,                              -- nullable, если клиент не в TG
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(master_id, phone)
);
CREATE INDEX ON clients (master_id, tg_id) WHERE tg_id IS NOT NULL;

CREATE TABLE appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    master_id UUID NOT NULL REFERENCES masters(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id),
    service_id UUID NOT NULL REFERENCES services(id),
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'pending', 'confirmed', 'rejected', 'cancelled', 'completed', 'no_show'
    )),
    source TEXT NOT NULL CHECK (source IN ('client_request', 'master_manual')),
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ,
    decision_deadline TIMESTAMPTZ,             -- до когда мастер должен ответить
    cancelled_at TIMESTAMPTZ,
    cancelled_by TEXT CHECK (cancelled_by IN ('client', 'master', 'system'))
);
CREATE INDEX ON appointments (master_id, start_at);
CREATE INDEX ON appointments (status, decision_deadline) WHERE status = 'pending';
CREATE UNIQUE INDEX uq_appointment_slot ON appointments (master_id, start_at)
    WHERE status IN ('pending', 'confirmed');

CREATE TABLE reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appointment_id UUID NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
    send_at TIMESTAMPTZ NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN (
        'day_before', 'two_hours', 'master_morning'
    )),
    channel TEXT NOT NULL DEFAULT 'telegram' CHECK (channel IN ('telegram', 'sms')),
    sent BOOLEAN NOT NULL DEFAULT FALSE,
    sent_at TIMESTAMPTZ
);
CREATE INDEX ON reminders (send_at) WHERE sent = FALSE;
```

### Статусы appointment — диаграмма переходов

```
          создание через клиента            создание вручную мастером
                  ↓                                   ↓
              [pending] ──(мастер подтвердил)──→ [confirmed]
                 │
                 ├─(мастер отклонил)──→ [rejected]  (финальный)
                 ├─(клиент отменил)──→  [cancelled] (финальный)
                 └─(timeout)──────────→ [cancelled] cancelled_by='system'

          [confirmed]
                 ├─(кто-то отменил)──→ [cancelled]
                 ├─(прошло время, клиент был)──→ [completed]
                 └─(прошло время, не пришёл)──→ [no_show]
```

---

## Флоу: клиент записывается сам

**Вход:** клиент открывает ссылку `t.me/{bot}?start=m_{master_short_id}`

**FSM-состояния:** `ChoosingService → ChoosingDate → ChoosingTime → EnteringName → EnteringPhone → Confirming → Done`

1. `/start m_{id}` → бот резолвит master по short_id → приветствие с именем клиники → кнопка «📝 Записаться».
2. Клиент жмёт — бот показывает активные услуги мастера списком (inline-кнопки).
3. Услуга выбрана → бот рисует inline-календарь на текущий месяц с раскраской:
   - Зелёный (`free`) — ≥5 свободных слотов
   - Жёлтый (`partial`) — 1–4 слота
   - Красный (`full`) — 0 слотов
   - Серый (`off`) — выходной/прошлое
4. День выбран → расчёт свободных слотов (см. services/availability.py) → сетка кнопок 3 в ряд, занятые слоты показаны серым/дизейблед (для прозрачности).
5. Слот выбран → спрашивает имя (reply-клавиатура «Использовать имя из Telegram»).
6. Спрашивает телефон (button `request_contact=True` для авто-отправки).
7. Показывает сводку → «✅ Отправить» / «✏️ Изменить».
8. Отправить → создаётся `appointment(status='pending', decision_deadline=NOW + master.decision_timeout_min)`.
   - Клиенту: «📨 Заявка отправлена, ждите подтверждения».
   - Мастеру: уведомление с inline-кнопками «✅ Подтвердить / ❌ Отклонить / 🕐 Другое время / 📋 История клиента».

---

## Флоу: мастер подтверждает/отклоняет заявку

**Callback data:** `ApprovalCallback(action='confirm|reject|alt_time', appointment_id=UUID)`

1. `confirm` → `appointment.status = 'confirmed'`, `confirmed_at = NOW()`.

   - Запланировать 2 напоминания клиенту (`day_before`, `two_hours`) через APScheduler.
   - Клиенту уходит «✅ Запись подтверждена».
   - Мастеру — «Готово» с кратким summary.

2. `reject` → `appointment.status = 'rejected'`.

   - Клиенту: «К сожалению, это время не подходит. Выберите другое: [кнопка]».

3. `alt_time` → мастеру показывается календарь с его свободными слотами → выбирает альтернативный слот → бот создаёт **новую** заявку с этим слотом (старая → `cancelled`) → клиенту: «Врач предлагает 16:30 вместо 15:00. Подходит? [Да / Выбрать другое]».

4. `history` → показывает все прошлые визиты этого клиента (inline-сообщение).

**Timeout handler:** фоновый таск (APScheduler, интервал 5 мин) ищет `appointments WHERE status='pending' AND decision_deadline < NOW()`, переводит в `cancelled` с `cancelled_by='system'`, уведомляет клиента.

---

## Флоу: мастер добавляет клиента вручную

**FSM-состояния:** `Starting → ChoosingClient → (EnteringNewClient) → ChoosingService → ChoosingDate → ChoosingTime → AddingComment → Confirming → Done`

1. Мастер: `/add` или кнопка «➕ Добавить запись».
2. Бот: «👤 Из моих клиентов / ➕ Новый клиент».
3. **Из моих** → поиск по имени/телефону (substring) → список результатов с кнопками.
   **Новый** → имя → телефон → создание записи в `clients`.
4. Дальше — услуга → календарь → слот (как у клиента, но **без pending** — сразу `confirmed`).
5. Опционально — комментарий («что делать»).
6. Сводка → «Сохранить» → `appointment(status='confirmed', source='master_manual')`.
7. Если у клиента есть `tg_id` — бот отправляет ему уведомление «Врач записал вас на …». Кнопка «Перенести» у клиента тоже работает.

---

## Флоу: мастер смотрит расписание

Команды и кнопки:

- **`/today`** — список на сегодня с эмодзи-статусами:
  - 🟢 confirmed
  - ⏳ pending
  - ✅ completed
  - ❌ cancelled/no_show
  - — свободный слот —
- **`/tomorrow`** — аналогично на завтра.
- **`/week`** — 7 дней со счётчиками записей, клик → день.
- **`/calendar`** — inline-календарь месяца с раскраской по загрузке, клик на день → расписание дня.
  - **Прошлые дни тоже доступны.** Показывается, кто приходил, с какими услугами, с возможностью пометить `completed/no_show` для каждой записи (если мастер забыл отметить раньше).
  - **Переключение месяцев** (← →) — видна вся история и будущее.
- **`/client <имя>`** — история клиента, все его визиты (прошлое + будущее).

---

## Расчёт свободных слотов (services/availability.py)

**Это чистая функция — покрывается юнит-тестами полностью, без БД.**

```python
def calculate_free_slots(
    work_hours: dict,          # {"mon": [["10:00","19:00"]], ...}
    breaks: dict,
    booked: list[tuple[datetime, datetime]],  # UTC
    day: date,
    tz: ZoneInfo,
    slot_step_min: int,
    service_duration_min: int,
) -> list[datetime]:
    """Возвращает список start-времён слотов (в локальной tz),
    куда влезает услуга duration_min минут."""
```

**Логика:**

1. Определить день недели → взять работающие интервалы.
2. Вычесть перерывы → получить "рабочие окна".
3. Вычесть занятые `booked` интервалы (конвертированные в локальную tz).
4. Каждое оставшееся окно нарезать на слоты с шагом `slot_step_min`.
5. Оставить только те слоты, где `slot_start + service_duration_min` ≤ конец окна.
6. Если `day == today` — отфильтровать прошедшие.

---

## Напоминания

**Когда планируем:**

- При переходе `appointment.status → 'confirmed'`:
  - `day_before` = `start_at - 24ч` (но если `start_at - 24ч < NOW`, то не создаём)
  - `two_hours` = `start_at - 2ч`

**Как отправляем:**

- APScheduler job: `send_due_reminders()` — раз в минуту.
- SQL: `SELECT * FROM reminders WHERE sent = FALSE AND send_at <= NOW() FOR UPDATE SKIP LOCKED LIMIT 100;`
- Для каждой: `SELECT * FROM appointments WHERE id = reminder.appointment_id` → если статус всё ещё `confirmed` — шлём, иначе пропускаем. После отправки `UPDATE reminders SET sent = TRUE, sent_at = NOW()`.

**При отмене записи** — удалять её будущие `reminders` (или просто не отправлять при проверке статуса).

---

## Защита от race condition

Два клиента одновременно выбирают один и тот же слот:

```python
async def create_appointment(session, master_id, client_id, service_id, start_at):
    try:
        appt = Appointment(..., status='pending')
        session.add(appt)
        await session.flush()  # тут сработает unique partial index
        await session.commit()
        return appt
    except IntegrityError:
        await session.rollback()
        raise SlotAlreadyTaken("Только что заняли, выберите другое")
```

Хэндлер ловит `SlotAlreadyTaken` → показывает клиенту обновлённую сетку слотов на этот день.

---

## i18n

- Армянский (hy) и русский (ru), английский позже.
- Формат — Fluent (.ftl), через `aiogram_i18n`.
- Мастер выбирает язык при `/start` и меняет в `/settings`.
- Язык клиента — по умолчанию такой же, как у мастера; можно переключить в боте.

---

## Конфигурация (.env)

```
BOT_TOKEN=
DATABASE_URL=postgresql+asyncpg://botik:botik@postgres:5432/botik
REDIS_URL=redis://redis:6379/0
ADMIN_TG_IDS=123456789,987654321  # для /admin команд на старте
LOG_LEVEL=INFO
SENTRY_DSN=                        # опционально
DEFAULT_TIMEZONE=Asia/Yerevan
```

---

## Безопасность

- **Валидация всех callback_data** через typed `CallbackData` классы.
- **Проверка владения**: мастер не может подтверждать чужие записи, клиент не видит чужих бронирований. Middleware `user.py` резолвит роль и прикрепляет к event'у.
- **Rate limiting** на уровне handler'ов: `aiogram.utils.chat_action.ChatActionMiddleware` + семафор на отправку (Telegram лимит — 30 msg/sec на бота).
- **Никакого SQL string formatting** — только parameterized queries через SQLAlchemy.
- **Логи без PII**: телефоны и имена не пишем в info-логи, только в debug (и в debug'е не на проде).
- **Бэкапы БД**: `pg_dump` по cron, кладётся в Backblaze B2 (или любой S3-совместимый).

---

## Тестирование

**Обязательно покрыть:**

- `services/availability.py` — 100% (чистая функция, много edge cases).
- `services/booking.py` — создание записи, подтверждение, отмена, race condition.
- `services/reminders.py` — планирование, отправка, идемпотентность.
- Handlers — через `aiogram` dispatcher test patterns + моки БД.

**Запуск:**

```bash
pytest tests/ -v --cov=src --cov-report=term-missing
```

**Цель покрытия:** services — 90%, handlers — 60% (тонкие).

---

## Деплой

### Локально

```bash
cp .env.example .env
# заполнить BOT_TOKEN
docker compose up -d
docker compose exec app alembic upgrade head
docker compose logs -f app
```

### Прод (Hetzner Cloud)

VPS: CX22 (2 vCPU, 4 GB RAM, €4/мес).

```bash
# на VPS
git clone <repo> /opt/botik
cd /opt/botik
cp .env.example .env  # заполнить prod-значения
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
docker compose exec app alembic upgrade head
```

**GitHub Actions** — по пушу в `main`: lint → тесты → SSH на VPS → `git pull && docker compose up -d --build`.

**Мониторинг:** Sentry для exceptions. Uptime — простой cron-пинг `/healthz`. Логи — `docker logs` + ротация.

**Бэкапы Postgres:**

```bash
# cron на VPS, каждый день в 4:00
docker compose exec -T postgres pg_dump -U botik botik | gzip > /backups/botik-$(date +\%F).sql.gz
# потом rclone → Backblaze B2
```

---

## Road Map

### v0.1 (MVP, 3 недели)

- Регистрация мастера, настройка услуг, часов работы.
- Клиент записывается сам → мастер подтверждает.
- Мастер добавляет клиента вручную.
- `/today`, `/week`, `/calendar` с просмотром прошлого и будущего.
- История клиента.
- Напоминания за 24ч и 2ч в Telegram.
- Ручная отмена и перенос.
- Один живой мастер на проде.

### v0.2 (недели 4–6)

- Multi-tenant (несколько мастеров, публичные ссылки).
- Веб-страница записи (как альтернатива боту — для тех, кто без TG).
- Статистика мастеру: загрузка по дням, количество no-show.

### v0.3+ (после 20–50 мастеров)

- Подписки и платежи (Idram/Telcell/Stripe).
- СМС-напоминания через локального провайдера.
- Команда мастеров в одной клинике (админ, расписание кабинетов).
- Google Calendar sync.
- Мобильное приложение (если понадобится — на старте не нужно).

---

## Что НЕ делать на MVP

- ❌ Платежи
- ❌ СМС
- ❌ Веб-дашборд / мобильное приложение
- ❌ Multi-master salon с админом
- ❌ Аналитика и графики
- ❌ Интеграция с Google Calendar
- ❌ AI-feature "умный помощник"

---

## Контакты и контекст

- **Регион:** Армения, Ереван и дальше.
- **Язык UI:** армянский + русский с первого дня.
- **Telezone:** `Asia/Yerevan` (UTC+4, без перехода на летнее время).
- **Телефоны:** формат `+374 XX XXX XXX`, normalize в `utils/phone.py`.
- **Валюта (когда понадобится):** AMD (драм).
