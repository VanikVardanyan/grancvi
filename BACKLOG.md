# BACKLOG.md

Атомарные задачи для Claude Code. Каждую можно скормить в отдельном git worktree параллельно (или последовательно).

Формат задачи: **заголовок → что сделать → критерии готовности → файлы, которые затрагивает**.

Перед каждой задачей Claude Code должен перечитать SPEC.md и CLAUDE.md.

---

## Эпик 1: Фундамент (неделя 1, дни 1–3)

### Задача 1.1. Инициализация проекта

**Что сделать:**
- Создать `pyproject.toml` с зависимостями (aiogram, sqlalchemy, asyncpg, alembic, redis, apscheduler, pydantic-settings, structlog, aiogram-i18n + fluent, pytest, pytest-asyncio, pytest-cov, ruff, mypy).
- Настроить `ruff` (line-length 100, target-version py312) и `mypy` (strict) в pyproject.
- Создать `Dockerfile` (python:3.12-slim, poetry или uv — выбери uv).
- Создать `docker-compose.yml` с сервисами: postgres:16, redis:7, app.
- Создать `.env.example` со всеми переменными из SPEC.md.
- Создать `.gitignore` (Python стандарт + .env).
- Создать скелет `src/main.py` с функцией `async def main()` и запуском aiogram polling (пока просто логирует "bot started" и /start отвечает "hello").
- `alembic init migrations` + настройка `alembic/env.py` на async SQLAlchemy и загрузку URL из env.

**Критерии готовности:**
- `docker compose up` поднимает всё, бот отвечает на /start «hello».
- `ruff check .` — 0 ошибок.
- `mypy src/` — 0 ошибок.
- `alembic current` работает.

**Файлы:** `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `.gitignore`, `src/main.py`, `src/config.py`, `src/db/base.py`, `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`.

---

### Задача 1.2. Модели БД и первая миграция

**Что сделать:**
- Создать `src/db/models.py` со всеми таблицами из SPEC.md (Master, Service, Client, Appointment, Reminder) на SQLAlchemy 2.0 (declarative с `Mapped[]`).
- Проверки (CHECK) на enum-значения (status, source, cancelled_by, kind, channel) — через `CheckConstraint`.
- Индексы, включая partial unique index на слот.
- Сгенерировать миграцию: `alembic revision --autogenerate -m "initial schema"`.
- Проверить сгенерированную миграцию — исправить руками, если `autogenerate` не понял partial index (он обычно не понимает).
- Применить: `alembic upgrade head`, убедиться что таблицы созданы.

**Критерии готовности:**
- Все таблицы и индексы существуют в Postgres.
- `alembic downgrade base && alembic upgrade head` работает без ошибок.
- Unique partial index на `(master_id, start_at) WHERE status IN ('pending','confirmed')` присутствует — проверить через `\d appointments` в psql.

**Файлы:** `src/db/models.py`, `migrations/versions/XXXX_initial_schema.py`.

---

### Задача 1.3. Middleware для БД и пользователя

**Что сделать:**
- `src/middlewares/db.py` — inject async session в handler через `data["session"]`. Commit в конце, rollback на исключении.
- `src/middlewares/user.py` — резолвит `Master` или `Client` из БД по `event.from_user.id`, кладёт в `data["master"]` / `data["client"]`. Если не найден — оставляет None (handler решает, что делать).
- Регистрация middleware в `main.py` для всех типов update'ов.

**Критерии готовности:**
- В handler'ах доступны `session`, `master`, `client` через аргументы.
- Session автоматически закрывается.

**Файлы:** `src/middlewares/db.py`, `src/middlewares/user.py`, обновление `src/main.py`.

---

## Эпик 2: Регистрация мастера и настройки (дни 3–4)

### Задача 2.1. FSM регистрации мастера

**Что сделать:**
- `/start` для незарегистрированного пользователя, чей tg_id в `ADMIN_TG_IDS` → запускает FSM регистрации мастера: имя → телефон → часовой пояс (по умолчанию Yerevan) → готово.
- Для уже зарегистрированного мастера `/start` показывает главное меню (reply-клавиатура): `/today`, `/add`, `/calendar`, `/settings`.
- Если tg_id не в ADMIN_TG_IDS и не нашёлся как клиент — отвечает «Нужна ссылка от клиники».

**Критерии готовности:**
- Новый пользователь из ADMIN_TG_IDS проходит регистрацию, запись в БД создана.
- Повторный /start показывает меню, не регистрирует заново.

**Файлы:** `src/fsm/master_register.py`, `src/handlers/master/start.py`, `src/keyboards/common.py`, `src/repositories/masters.py`.

---

### Задача 2.2. Управление услугами мастера

**Что сделать:**
- Команда `/services` (или из меню `/settings → Услуги`) → список активных услуг с inline-кнопками ✏️ (редактировать) и 🗑 (удалить).
- Кнопка «➕ Добавить услугу» → FSM: название → длительность (минуты) → сохранить.
- Редактирование: кнопки изменить название / изменить длительность / переключить active.

**Критерии готовности:**
- Мастер может добавлять, редактировать, удалять/деактивировать услуги.
- Удалённая услуга (active=False) не показывается клиентам, но прошлые записи на неё остаются.

**Файлы:** `src/fsm/services.py`, `src/handlers/master/services.py`, `src/repositories/services.py`, `src/callback_data/services.py`.

---

### Задача 2.3. Настройка часов работы

**Что сделать:**
- `/settings → Часы работы` → inline-клавиатура с днями недели, рядом — часы работы или «выходной».
- Клик на день → FSM: начало → конец (или сразу «выходной»). Поддержать split-day (утро+вечер, если надо) через опцию «добавить ещё интервал».
- Перерывы (обед) — отдельная команда `/settings → Перерывы`, аналогично.
- Сохранение в `masters.work_hours` и `masters.breaks` (JSONB).

**Критерии готовности:**
- Мастер задаёт часы работы на каждый день.
- Данные корректно сохраняются в JSONB.
- При расчёте слотов (следующая задача) используются эти часы.

**Файлы:** `src/fsm/work_hours.py`, `src/handlers/master/settings.py`, `src/keyboards/settings.py`.

---

## Эпик 3: Доступность слотов (день 5)

### Задача 3.1. Чистая функция availability

**Что сделать:**
- `src/services/availability.py` — функция `calculate_free_slots(work_hours, breaks, booked, day, tz, slot_step_min, service_duration_min) -> list[datetime]` по сигнатуре из SPEC.md.
- 100% покрытие юнит-тестами в `tests/test_availability.py`:
  - Пустой день (нет записей) → вся сетка свободна.
  - Одна запись посередине → слоты до и после, но не пересекающиеся.
  - Перерыв-обед → слоты до и после обеда.
  - Выходной → пустой список.
  - Сегодня → прошедшие слоты отфильтрованы.
  - Услуга длиннее, чем окно → никаких слотов.
  - Граничные случаи: запись начинается точно в начале рабочего дня / заканчивается точно в конце.
  - Split-day (утро + вечер, с разрывом не-обед).

**Критерии готовности:**
- Функция чистая (без БД, без now()).
- `pytest tests/test_availability.py -v --cov=src.services.availability` — 100%.

**Файлы:** `src/services/availability.py`, `tests/test_availability.py`.

---

### Задача 3.2. Репозиторий и сервис бронирования

**Что сделать:**
- `repositories/appointments.py`: методы `get_booked_for_day(master_id, day, tz)`, `create(...)`, `update_status(...)`, `get_pending_past_deadline()`.
- `services/booking.py`: `BookingService` с методами:
  - `get_free_slots(master, service, day) -> list[datetime]` — вызывает availability + repository.
  - `create_pending(master, client_data, service, start_at) -> Appointment` — создаёт запись, ловит IntegrityError → `SlotAlreadyTaken`.
  - `confirm(appointment_id, master_id) -> Appointment` — меняет статус, ставит confirmed_at, планирует напоминания (вызов ReminderService.schedule).
  - `reject(appointment_id, master_id, reason=None)`.
  - `cancel(appointment_id, cancelled_by)`.
  - `create_manual(master, client, service, start_at, comment) -> Appointment` — сразу confirmed.
- Кастомные исключения в `src/exceptions.py`: `SlotAlreadyTaken`, `NotFound`, `InvalidState`.

**Критерии готовности:**
- Тесты на все happy paths + race condition (запустить 2 параллельные попытки создать на один слот → одна прошла, вторая получила `SlotAlreadyTaken`).
- Покрытие services/booking.py ≥90%.

**Файлы:** `src/repositories/appointments.py`, `src/services/booking.py`, `src/exceptions.py`, `tests/test_booking.py`.

---

## Эпик 4: FSM клиентской записи (дни 6–7)

### Задача 4.1. Inline-календарь с раскраской

**Что сделать:**
- `src/keyboards/calendar.py` — функция `build_calendar(master_id, year, month, availability_map) -> InlineKeyboardMarkup`.
  - 7 колонок (Пн–Вс), 5–6 рядов.
  - Заголовок с месяцем и кнопками «‹» «›» для переключения.
  - Клетки: день + эмодзи по загрузке (🟢 / 🟡 / 🔴 / —).
  - Прошлые дни — `callback_data="noop"` или без callback.
  - `CalendarCallback(action="select|prev|next|noop", year, month, day)`.
- Функция подсчёта загрузки дня: для каждого дня месяца — сколько свободных слотов осталось (относительно средней длительности услуги), возвращает `"free" | "partial" | "full" | "off"`.

**Критерии готовности:**
- Календарь корректно отображается, навигация месяцев работает.
- Раскраска отражает реальную загрузку из БД.

**Файлы:** `src/keyboards/calendar.py`, `src/callback_data/calendar.py`, `src/services/availability.py` (добавить `day_load()`).

---

### Задача 4.2. Клиентский флоу бронирования

**Что сделать:**
- `/start m_{short_id}` → резолвит master → приветствие → «📝 Записаться».
- FSM `ClientBooking`: ChoosingService → ChoosingDate → ChoosingTime → EnteringName → EnteringPhone → Confirming.
- На каждом шаге — кнопка «← Назад» и «Отмена».
- Сохранить / обновить запись в `clients` по `(master_id, phone)`.
- Создать `appointment` через `BookingService.create_pending`.
- Отправить клиенту «Заявка отправлена».
- Отправить мастеру уведомление (следующая задача — обработчик уведомлений).

**Критерии готовности:**
- Клиент проходит весь флоу, запись создаётся в статусе `pending`.
- При попытке выбрать занятый слот — показывает обновлённую сетку.
- Все тексты через i18n (на старте только ключи, переводы можно пустые поставить и заполнить позже).

**Файлы:** `src/fsm/client_booking.py`, `src/handlers/client/booking.py`, `src/handlers/client/start.py`, `src/keyboards/slots.py`, `src/repositories/clients.py`.

---

### Задача 4.3. Уведомление мастеру и обработка callback'ов

**Что сделать:**
- При создании pending-записи — `bot.send_message(master.tg_id, ...)` с inline-клавиатурой: «✅ Подтвердить», «❌ Отклонить», «🕐 Другое время», «📋 История клиента».
- `ApprovalCallback(action, appointment_id)` — обработчик:
  - `confirm` → `BookingService.confirm` → уведомления.
  - `reject` → `BookingService.reject` → клиенту «отклонено, выберите другое».
  - `alt_time` → мастеру календарь → выбирает новый слот → создаёт новую запись → старая отменяется → клиенту предлагают новое время.
  - `history` → показать прошлые записи клиента (edit_message или новое сообщение).

**Критерии готовности:**
- Мастер видит уведомление, может подтвердить/отклонить.
- Клиент получает правильное сообщение об исходе.
- `alt_time` работает корректно (новая pending создаётся, старая cancelled).

**Файлы:** `src/handlers/master/approve.py`, `src/callback_data/approval.py`, обновление `src/services/booking.py`.

---

## Эпик 5: Ручное добавление мастером (день 8)

### Задача 5.1. FSM `/add` для мастера

**Что сделать:**
- Команда `/add` → FSM: выбор клиента (из существующих / новый).
- Поиск клиента: мастер вводит строку → repository метод `search_by_master(master_id, query)` ищет по substring в name и phone.
- Выбран клиент → услуга → календарь → слот → опциональный комментарий → подтверждение.
- Запись создаётся сразу `confirmed`, source='master_manual'.
- Если у клиента есть tg_id — отправить ему уведомление «Врач записал вас на …» с кнопкой «Перенести».

**Критерии готовности:**
- Мастер может создать запись за 5–7 нажатий.
- Клиент с Telegram получает уведомление.

**Файлы:** `src/fsm/master_add.py`, `src/handlers/master/add_manual.py`, обновление `src/repositories/clients.py`.

---

## Эпик 6: Просмотр расписания (дни 9–10)

### Задача 6.1. /today и /tomorrow

**Что сделать:**
- Команда `/today` — список всех записей на сегодня + помеченные свободные слоты в рабочие часы.
- Каждая запись — строка с эмодзи-статусом, временем, именем клиента, услугой.
- Inline-кнопки под сообщением: «📅 Завтра», «🗓 На неделю», «➕ Добавить».
- `/tomorrow` — аналогично.

**Критерии готовности:**
- Формат как в прототипе (см. booking-bot-prototype.html).
- Прошедшие записи сегодняшнего дня показаны с другим эмодзи (completed / no_show / отмена).

**Файлы:** `src/handlers/master/today.py`, `src/utils/format.py`.

---

### Задача 6.2. /week и /calendar с навигацией

**Что сделать:**
- `/week` — 7 дней от сегодня с `день + дата + count записей + визуализацией загрузки (▓▓▓░░░░░)`. Клик на день → /day-view.
- `/calendar` — inline-календарь месяца (переиспользуй keyboards/calendar.py). Клик → расписание дня. Навигация месяцев ← →, **включая прошлые месяцы**.
- Расписание прошлого дня — показывает, кто приходил, inline-кнопки «✅ Был» / «❌ Не пришёл» для записей, которые ещё в статусе `confirmed` (мастер мог забыть пометить).

**Критерии готовности:**
- Навигация месяцев работает и назад, и вперёд.
- Мастер может в любой момент пометить completed/no_show для прошлых записей.

**Файлы:** `src/handlers/master/week.py`, `src/handlers/master/calendar.py`.

---

### Задача 6.3. История клиента

**Что сделать:**
- Команда `/client <имя или телефон>` → если одно совпадение — показать историю, если несколько — список с inline-кнопками.
- Страница клиента: имя, телефон, заметки (редактируемые), список всех записей (прошлые + будущие) по хронологии.
- Inline-кнопки: «✏️ Редактировать заметки», «➕ Добавить запись этому клиенту».

**Критерии готовности:**
- Мастер быстро находит клиента и видит всю историю.

**Файлы:** `src/handlers/master/client_history.py`.

---

## Эпик 7: Напоминания (день 11)

### Задача 7.1. Планировщик и job'ы

**Что сделать:**
- `src/scheduler/setup.py` — `setup_scheduler(bot)` возвращает AsyncIOScheduler с Redis jobstore.
- `src/scheduler/jobs.py`:
  - `send_due_reminders(bot)` — раз в минуту: SELECT reminders WHERE sent=false AND send_at <= now() FOR UPDATE SKIP LOCKED → проверяет appointment.status → отправляет → UPDATE sent=true.
  - `expire_pending_appointments(bot)` — раз в 5 минут: находит pending с decision_deadline < now(), переводит в cancelled (cancelled_by='system'), уведомляет клиента.
- `src/services/reminders.py`:
  - `schedule_for_appointment(appointment)` — создаёт 2 записи в `reminders` (day_before и two_hours), пропускает если уже прошло.
  - `cancel_for_appointment(appointment_id)` — удаляет или помечает reminders для отменённой записи.
- Интеграция в `main.py`: scheduler запускается вместе с ботом, shutdown корректный.

**Критерии готовности:**
- Напоминания уходят в правильное время (проверить с ускоренной настройкой на тесте).
- Pending с просроченным deadline корректно отменяются.
- Идемпотентность: при повторном запуске job'а одно и то же напоминание не отправляется дважды.

**Файлы:** `src/scheduler/setup.py`, `src/scheduler/jobs.py`, `src/services/reminders.py`, `tests/test_reminders.py`.

---

### Задача 7.2. Обработка ответов клиента на напоминания

**Что сделать:**
- Напоминание за 24ч — с inline-кнопками «👍 Буду», «✏️ Перенести».
- Напоминание за 2ч — просто текст, без кнопок (уже поздно переносить).
- `👍 Буду` → спасибо, ничего не меняет.
- `✏️ Перенести` → FSM: новый календарь → слот → создание новой заявки (pending) → старая отменяется → мастеру уведомление.

**Критерии готовности:**
- Клиент может перенести запись в один flow, без звонка врачу.

**Файлы:** `src/handlers/client/reminders_reply.py`, `src/fsm/client_reschedule.py`.

---

## Эпик 8: i18n, полировка, деплой (дни 12–14)

### Задача 8.1. Локализация армянский + русский

**Что сделать:**
- `locales/ru/LC_MESSAGES/bot.ftl` и `locales/hy/LC_MESSAGES/bot.ftl` — все тексты.
- Middleware i18n, использующий `master.lang` или `client.lang`.
- Fallback на русский, если ключа нет в армянском.

**Критерии готовности:**
- Переключение языка работает.
- Все тексты переведены на оба языка (армянский можно сначала взять через ChatGPT, потом показать армяноговорящему на вычитку).

**Файлы:** `locales/*/bot.ftl`, `src/middlewares/i18n.py`.

---

### Задача 8.2. Docker-прод и CI

**Что сделать:**
- `docker-compose.prod.yml` — оверрайд: restart: always, no exposed ports кроме внутренних, env_file для секретов.
- `.github/workflows/ci.yml` — на push в main: setup python → pip install → ruff → mypy → pytest. На успех + main — SSH на VPS → git pull → docker compose build → up -d.
- Secrets в GitHub: `SSH_HOST`, `SSH_USER`, `SSH_KEY`, `BOT_TOKEN_PROD`.
- Healthcheck endpoint (простой aiohttp-сервер внутри бота на 8080/healthz).

**Критерии готовности:**
- Push в main → через 2 минуты обновлённый бот работает на VPS.
- Healthcheck отвечает 200 OK.

**Файлы:** `docker-compose.prod.yml`, `.github/workflows/ci.yml`, `src/healthcheck.py`.

---

### Задача 8.3. Скрипт бэкапов

**Что сделать:**
- `scripts/backup.sh` — `pg_dump` в gz, `rclone copy` в Backblaze B2.
- Документация в README: как настроить cron на VPS (`0 4 * * * /opt/botik/scripts/backup.sh`).
- Ретеншн: хранить 30 дней дневных бэкапов + 12 месяцев месячных.

**Критерии готовности:**
- Backup создаётся, загружается в B2, старые удаляются.

**Файлы:** `scripts/backup.sh`, `README.md` (секция про бэкапы).

---

## Как работать с этим бэклогом через Claude Code

1. **Начать с задачи 1.1** в основном репо.
2. Для задач из разных эпиков (например, 3.1 и 4.1) можно использовать git worktrees параллельно: `claude --worktree epic-3-availability`.
3. Перед каждой задачей Claude Code должен прочитать SPEC.md и CLAUDE.md.
4. После задачи — коммит, PR review (даже на solo-разработке — полезно самому перечитать), merge.
5. Каждый эпик заканчивается функциональной вехой, которую можно реально опробовать в Telegram.

## Рекомендация по промпту для Claude Code

Пример промпта для задачи:

```
Read SPEC.md and CLAUDE.md first. Then implement Задача 1.1 from BACKLOG.md: 
"Инициализация проекта". Follow all architecture and code-style rules strictly. 
After implementation, run ruff + mypy and confirm they pass. Show me the file tree 
and the main.py content. Do NOT implement anything beyond this task.
```

Держи промпты короткими и явными. Одна задача — один промпт. Не давай размытых «сделай бота».
