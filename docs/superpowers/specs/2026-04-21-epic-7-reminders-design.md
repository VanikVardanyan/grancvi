# Эпик 7: Напоминания — дизайн-спека

**Дата:** 2026-04-21
**Статус:** утверждён пользователем, готов к планированию
**Scope:** инфраструктура напоминаний (клиент T-24h, T-2h; мастер T-15min) + авто-экспайр просроченных pending. Кнопки «Буду»/«Перенести» и FSM переноса — **не в этом эпике**, будут отдельной спекой.

---

## Цель

Записи, подтверждённые мастером, автоматически напоминают клиенту (за 24ч, за 2ч) и мастеру (за 15 мин). Заявки `pending`, которые мастер не обработал до `decision_deadline`, автоматически отменяются с уведомлением клиента.

## Архитектура

**Подход:** polling (раз в минуту один tick читает `reminders WHERE sent=false AND send_at <= now FOR UPDATE SKIP LOCKED`). Источник правды — БД; APScheduler запускает только два периодических job'а. Альтернатива с индивидуальными job'ами на каждое `send_at` отметена: SPEC явно требует polling, восстановление после рестарта тривиально, нагрузка в модели one-master-per-bot мизерная.

### Новые файлы

- `src/scheduler/__init__.py` — пустой (пакет).
- `src/scheduler/setup.py` — `build_scheduler(redis_url) -> AsyncIOScheduler` с `RedisJobStore`.
- `src/scheduler/jobs.py` — две async-функции:
  - `send_due_reminders(bot, session_factory)` — раз в минуту.
  - `expire_pending_appointments(bot, session_factory)` — раз в 5 минут.
- `src/services/reminders.py` — `ReminderService`:
  - `schedule_for_appointment(appointment)` — создаёт до 3 строк `reminders`.
  - `suppress_for_appointment(appointment_id)` — помечает все незапущенные напоминания как `sent=true` (без отправки).
- `src/repositories/reminders.py` — `ReminderRepository`:
  - `insert_many(rows)` — batch insert с `ON CONFLICT DO NOTHING` на `(appointment_id, kind)`.
  - `get_due_for_update(now, limit=100)` — `JOIN appointments` + `FOR UPDATE OF reminders SKIP LOCKED`.
  - `mark_sent(reminder_id, sent_at)`.
  - `suppress_for_appointment(appointment_id, now)` — `UPDATE ... SET sent=true, sent_at=now WHERE appointment_id=$1 AND sent=false`.
- Миграция Alembic.

### Интеграция с существующими сервисами

- `BookingService.confirm(...)` (Эпик 4) — после commit: `await reminder_service.schedule_for_appointment(appointment)`.
- `BookingService.create_from_master(...)` / путь `/add` (Эпик 5, создаёт сразу confirmed) — тоже `schedule_for_appointment`.
- `BookingService.cancel(...)`, `cancel_by_client(...)`, `reject(...)` — добавить вызов `suppress_for_appointment(appointment_id)`.
- `BookingService.mark_completed(...)`, `mark_no_show(...)` — **не трогать** (это прошлое, напоминания уже либо отправились, либо засуппресснуты).

### Лайфспан

В `main.py`:

1. На старте:
   ```python
   scheduler = build_scheduler(settings.redis_url)
   session_factory = async_sessionmaker(engine, expire_on_commit=False)
   scheduler.add_job(
       send_due_reminders, CronTrigger(minute="*"),
       id="send_due_reminders", replace_existing=True,
       kwargs={"bot": bot, "session_factory": session_factory},
   )
   scheduler.add_job(
       expire_pending_appointments, CronTrigger(minute="*/5"),
       id="expire_pending_appointments", replace_existing=True,
       kwargs={"bot": bot, "session_factory": session_factory},
   )
   scheduler.start()
   ```
2. На shutdown: `scheduler.shutdown(wait=True)` → `await dp.stop_polling()` → `await engine.dispose()`.

`replace_existing=True` + фиксированные `id` гарантируют, что при рестарте не копятся дубликаты job'ов в Redis jobstore.

## Планирование (`schedule_for_appointment`)

Вход: `Appointment` (`id`, `start_at`, `master_id`, `client_id`, `service_id`).

Логика:

```
now = now_utc()
candidates = [
    ("day_before",    start_at - 24h, client),
    ("two_hours",     start_at - 2h,  client),
    ("master_before", start_at - 15m, master),
]
rows = [(appointment_id, kind, send_at, channel="telegram")
        for kind, send_at, _ in candidates if send_at > now]
repo.insert_many(rows)  # ON CONFLICT (appointment_id, kind) DO NOTHING
```

**15min — хардкод.** Когда понадобится другая цифра — вынесем в настройку. YAGNI.

**Идемпотентность:** unique constraint `(appointment_id, kind)` + `ON CONFLICT DO NOTHING` означает, что повторный вызов (например, если handler повторно обработает callback) не создаст дубликатов.

## Подавление (`suppress_for_appointment`)

Вызов: на `cancel_by_client`, `cancel` (мастером), `reject` (pending → cancelled system'ом через job экспайра).

SQL: `UPDATE reminders SET sent=true, sent_at=$now WHERE appointment_id=$1 AND sent=false`.

**Почему не DELETE:** сохраняем аудит — видно, что напоминание было, но не было отправлено.

**Дублирующая защита в воркере:** даже если suppress не успел отработать (race), воркер перед отправкой проверяет `appointment.status=='confirmed'` — для cancelled/rejected пропустит с пометкой `sent=true`.

## Воркер `send_due_reminders`

**Cadence:** `CronTrigger(minute="*")`.

**Шаги (одна транзакция на тик):**

1. Открыть session через `session_factory`.
2. Репо: `get_due_for_update(now, limit=100)` возвращает список кортежей `(Reminder, Appointment, Master, Client, Service)` (joined). SQL:
   ```sql
   SELECT r.*, a.*, m.*, c.*, s.*
   FROM reminders r
   JOIN appointments a ON r.appointment_id = a.id
   JOIN masters m ON a.master_id = m.id
   JOIN clients c ON a.client_id = c.id
   JOIN services s ON a.service_id = s.id
   WHERE r.sent = false AND r.send_at <= $now
   ORDER BY r.send_at
   LIMIT 100
   FOR UPDATE OF r SKIP LOCKED
   ```
3. Для каждого кортежа:
   - Если `a.status != 'confirmed'` → `r.sent=true, r.sent_at=now`, continue (ленивая чистка мёртвых напоминаний).
   - Определить `chat_id`:
     - `kind in ("day_before", "two_hours")` → `c.telegram_id`
     - `kind == "master_before"` → `m.telegram_id`
   - Сформатировать текст по `kind` (см. секцию «Тексты»).
   - `try: await bot.send_message(chat_id, text)`:
     - Успех → `r.sent=true, r.sent_at=now`.
     - `TelegramRetryAfter` → оставить `sent=false`, лог warning, continue (следующий тик подхватит).
     - `TelegramForbiddenError` / `TelegramBadRequest` (пользователь заблокировал бота, неверный chat_id) → `r.sent=true, r.sent_at=now`, лог warning, continue (не ретраим).
     - Любое другое `Exception` → оставить `sent=false`, лог error (ретрай на следующем тике).
4. `commit`.

**Лимит 100:** защита от взрыва очереди. Для one-master-per-bot никогда не упрётся, дешёвая подушка.

**Идемпотентность:** `FOR UPDATE SKIP LOCKED` + `sent=true` flag не дают отправить дважды.

## Воркер `expire_pending_appointments`

**Cadence:** `CronTrigger(minute="*/5")`.

**Шаги:**

1. `repo = AppointmentRepository(session)`.
2. `pending = await repo.get_pending_past_deadline(now=now_utc())` (метод уже есть из Эпика 4).
3. Для каждого:
   - `await booking_service.cancel(p.id, cancelled_by='system')` — переводит в cancelled, коммитит. Сигнатура `cancel(appointment_id, *, cancelled_by, now=None)` уже принимает `cancelled_by: str` (Эпик 4).
   - Текст: `strings.REMINDER_PENDING_EXPIRED.format(date=..., time=..., service=...)`.
   - `try: await bot.send_message(client.telegram_id, text)` (те же исключения что и в send_due_reminders).
   - Мастера не уведомляем — это его бездействие привело к отмене.
4. `suppress_for_appointment(p.id)` вызовется изнутри `cancel` (через добавляемый в Эпике 7 хук).

**Устойчивость:** если job крэшнулся посередине — следующий тик добьёт (`status='pending'` + `deadline < now` — устойчивая выборка).

## Тексты (RU)

Новые ключи в `_RU` блоке `src/strings.py`:

```python
"REMINDER_CLIENT_DAY_BEFORE": "⏰ Напоминание: завтра в {time} — {service}.\nЖдём вас!",
"REMINDER_CLIENT_TWO_HOURS": "⏰ Через 2 часа у вас запись: {service}, {time}.",
"REMINDER_MASTER_BEFORE": "⏰ Через 15 минут: {client_name} — {service}.\n📞 {phone}",
"REMINDER_PENDING_EXPIRED": (
    "К сожалению, мастер не подтвердил вашу заявку на {date} {time} — {service}.\n"
    "Попробуйте выбрать другое время: /start"
),
```

Параметры:
- `{time}` — `HH:MM` в TZ мастера.
- `{date}` — `DD.MM` в TZ мастера.
- `{service}` — `service.name`.
- `{client_name}` — `client.name`.
- `{phone}` — `client.phone` (обязательное поле, всегда есть).

HY — в финальной задаче плана, переводит пользователь.

## Миграция

Одна ревизия `xxxx_epic_7_reminders`:

1. Обновить данные (на всякий случай): `UPDATE reminders SET kind='master_before' WHERE kind='master_morning'`.
2. Переименовать check-constraint: `DROP CONSTRAINT ck_reminders_kind`, `ADD CONSTRAINT ck_reminders_kind CHECK (kind IN ('day_before', 'two_hours', 'master_before'))`.
3. Добавить `UniqueConstraint('appointment_id', 'kind', name='uq_reminders_appointment_kind')`.

Downgrade — обратные шаги.

## Тестирование

### `ReminderService` (pure unit)

- `schedule_for_appointment`: `start_at` через 26ч → вставлены все 3; через 23ч → 2 (day_before пропущен); через 1ч → 1 (только master_before); через 10 мин → 0.
- `suppress_for_appointment`: помечает только `sent=false` записи, не трогает уже отправленные.

### `ReminderRepository` (БД-тест с фикстурами)

- `insert_many` + повторный вызов с теми же `(appointment_id, kind)` → второй проход не создаёт дубликаты (ON CONFLICT).
- `get_due_for_update` возвращает правильный набор (фильтр по `sent=false AND send_at <= now`).
- `mark_sent` идемпотентен.

### Job `send_due_reminders` (интеграционно, тестовая БД + fake `Bot`)

- confirmed + due → отправлено, `sent=true`, fake Bot получил `send_message` с правильным `chat_id` и шаблоном.
- cancelled + due → `sent=true`, но Bot **не** вызван.
- due в будущем → нетронуто.
- `TelegramBadRequest` (бот заблокирован) → `sent=true`, лог warning.
- `TelegramRetryAfter` → `sent=false`, следующий запуск повторяет.
- Повторный запуск на том же состоянии → отправка не дублируется.

### Job `expire_pending_appointments`

- pending с `deadline < now` → `status='cancelled'`, `cancelled_by='system'`, клиент получил `REMINDER_PENDING_EXPIRED`.
- pending с `deadline > now` → нетронут.
- confirmed с `deadline < now` → нетронут (нерелевантное поле для confirmed).

### Интеграция с `BookingService`

- `confirm` создаёт 3 строки в `reminders`.
- `cancel` / `cancel_by_client` / `reject` помечают все будущие reminders `sent=true`.
- `/add` создаёт confirmed appointment + 3 reminders.

### Что НЕ тестируем

- APScheduler runtime — job-функции дёргаются напрямую в тестах. Cron-триггеры верим APScheduler'у.
- Redis jobstore — верим библиотеке.

## Критерии готовности

- [ ] При `confirm` в БД появляется 3 reminders.
- [ ] При `cancel` все reminders записи `sent=true`.
- [ ] Воркер раз в минуту отправляет due reminders и помечает их `sent=true`.
- [ ] Воркер пропускает reminders записи, сменившей статус на `cancelled`, но отмечает их `sent=true`.
- [ ] `expire_pending_appointments` раз в 5 минут переводит просроченные pending в cancelled и шлёт клиенту уведомление.
- [ ] Идемпотентность: повторный запуск job на одном и том же состоянии не шлёт одно и то же дважды.
- [ ] `mypy --strict`, `ruff check`, `ruff format --check`, `pytest -q` — все зелёные.

## Файлы

**Создать:**
- `src/scheduler/__init__.py`
- `src/scheduler/setup.py`
- `src/scheduler/jobs.py`
- `src/services/reminders.py`
- `src/repositories/reminders.py`
- `alembic/versions/xxxx_epic_7_reminders.py`
- `tests/test_services_reminders.py`
- `tests/test_repositories_reminders.py`
- `tests/test_scheduler_jobs.py`

**Модифицировать:**
- `src/main.py` — лайфспан scheduler'а.
- `src/services/booking.py` — вызовы `schedule_for_appointment` / `suppress_for_appointment`.
- `src/handlers/master/add_manual.py` — вызов `schedule_for_appointment` после создания confirmed.
- `src/db/models.py` — обновить `REMINDER_KINDS = ("day_before", "two_hours", "master_before")`, добавить unique constraint.
- `src/strings.py` — 4 новых ключа в `_RU` (в HY — финальной задачей).

## Out of scope

- Inline-кнопки «👍 Буду» / «✏️ Перенести» на напоминаниях.
- FSM переноса записи клиентом.
- Уведомление мастеру при автоотмене pending.
- Конфигурируемое смещение мастерского напоминания.
- SMS-канал (в БД уже поддержан `channel`, но отправка только telegram).
