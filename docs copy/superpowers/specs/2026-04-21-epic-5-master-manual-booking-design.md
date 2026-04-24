# Эпик 5 — Ручное добавление записи мастером (`/add`)

**Дата:** 2026-04-21
**Статус:** Design — утверждён пользователем
**Предыдущие эпики:** 1 (foundation), 2 (master FSM + services CRUD), 3 (BookingService), 4 (client booking FSM + master approval) — закрыты.

---

## Goal

Команда `/add` позволяет мастеру вручную завести запись для клиента, который позвонил или пришёл офлайн. Мастер сам выбирает услугу, дату, время, клиента; запись создаётся сразу как `status='confirmed', source='master_manual'`. Если у клиента есть `tg_id` — ему приходит уведомление с кнопкой «Отменить».

## Архитектура

Линейный FSM `MasterAdd` из 9 состояний, один Router в `src/handlers/master/add_manual.py`. Переиспользуем клавиатуры и `CallbackData` из Эпика 4 (`services_pick_kb`, `calendar_kb`, `ClientServicePick`, `CalendarCallback`, `SlotCallback`). Новые `CallbackData` префиксы ≤4 символов. Все даты — UTC в БД, Yerevan на границе. Гейт на входе — `_IsMasterOrAdmin` (уже есть).

Полный override рабочих часов опциональный — через отдельное состояние `EnteringCustomTime` после кнопки «➕ Нестандартное время» в сетке слотов. Унивкальный индекс БД защищает от дабл-букинга в любом случае.

## FSM `MasterAdd`

| Состояние | Вход | Выход |
|---|---|---|
| `PickingClient` | `/add` | выбран клиент из recent → `PickingService`; 🔍 → `SearchingClient`; ➕ → `NewClientName` |
| `SearchingClient` | из `PickingClient` | ввод подстроки → результаты (тот же `RecentClientCallback`) → клик → `PickingService` |
| `NewClientName` | из `PickingClient` (➕) | ввод имени (≥2 симв.) → `NewClientPhone` |
| `NewClientPhone` | из `NewClientName` | валидный +374… → проверка дедупа. Дедуп: `phone_dup_kb`, state не меняется; `use` → `PickingService`, `retry` → тот же state |
| `PickingService` | из любого клиент-шага | `ClientServicePick` → `PickingDate` |
| `PickingDate` | из `PickingService` | `CalendarCallback` prev/next — тот же state; pick → `PickingSlot` |
| `PickingSlot` | из `PickingDate` | `SlotCallback` → `EnteringComment`; `CustomTimeCallback` → `EnteringCustomTime`; «Назад» → `PickingDate` |
| `EnteringCustomTime` | из `PickingSlot` | ввод `ДД.ММ ЧЧ:ММ` / `ЧЧ:ММ` → `EnteringComment` |
| `EnteringComment` | из `PickingSlot` / `EnteringCustomTime` | текст → `Confirming`; `SkipCommentCallback` → `Confirming` с `notes=None` |
| `Confirming` | из `EnteringComment` | ✅ Сохранить → `create_manual` → state.clear(); ❌ Отмена → state.clear() |

`/cancel` на любом шаге: `state.clear()` + «Отменено.»

## UX-решения (принятые в брейнстормe)

1. **Выбор клиента:** по умолчанию последние 10 (по `MAX(appointment.start_at) DESC NULLS LAST`, клиенты без записей в конце по `created_at DESC`), плюс кнопки «🔍 Поиск» и «➕ Новый». Поиск — подстрока в имени и в цифрах телефона.
2. **Override рабочих часов:** default-путь — только свободные слоты внутри `work_hours` / `slot_step_min` (как у клиента); в сетке есть кнопка «➕ Нестандартное время», которая ведёт в `EnteringCustomTime` для ввода произвольной даты/времени без валидации рабочих часов и шага (уникальный индекс БД защитит от дабл-букинга).
3. **Кнопка «Отменить» у клиента:** в Эпике 5 — только кнопка «❌ Отменить запись» в клиентском уведомлении. Полноценный «Перенести» (новый booking FSM для клиента) отложен в будущий эпик. Отмена = `status='cancelled'` + уведомление мастеру.
4. **Дедуп по телефону:** если `phone` нового клиента совпал с существующим у этого мастера — диалог «По этому номеру уже есть „Имя". Использовать?» [Да] / [Отмена — ввести другой]. Имя существующего клиента не перезаписывается.
5. **Комментарий:** отдельное состояние FSM `EnteringComment` с кнопкой «⏭ Пропустить». Хранится в `Appointment.comment` (название колонки в модели — `comment`, не `notes`). Длина ≤200 символов (обрезаем).

## Файлы

### Новые

- `src/fsm/master_add.py` — `class MasterAdd(StatesGroup)` с 9 состояниями.
- `src/callback_data/master_add.py` — `RecentClientCallback`, `PhoneDupCallback`, `SkipCommentCallback`, `CustomTimeCallback`.
- `src/keyboards/master_add.py` — `recent_clients_kb`, `search_results_kb`, `phone_dup_kb`, `slots_grid_with_custom`, `skip_comment_kb`, `confirm_add_kb`, `client_cancel_kb`.
- `src/handlers/master/add_manual.py` — роутер, все хэндлеры /add.
- `src/handlers/client/cancel.py` — хэндлер отмены клиентом (`ApprovalCallback(action="cancel")`).
- Тесты: `tests/test_repositories_clients_epic5.py`, `tests/test_services_booking_epic5.py`, `tests/test_handlers_master_add.py`, `tests/test_handlers_client_cancel.py`.

### Изменяемые

- `src/repositories/clients.py` — добавить `list_recent_by_master(master_id, limit=10)` и `search_by_master(master_id, query, limit=10)`.
- `src/services/booking.py` — `create_manual` уже есть, не трогаем. Добавить `cancel_by_client(appointment_id, tg_id)` — обёртка над `cancel`.
- `src/callback_data/approval.py` — расширить `ApprovalCallback.action` значением `"cancel"`. (файл называется `approval.py`, не `booking.py`)
- `src/handlers/master/__init__.py` — `include_router(add_manual.router)`.
- `src/handlers/client/__init__.py` — `include_router(cancel.router)`.
- `src/strings.py` — добавить новые ключи в оба бандла `_RU` и `_HY`.

## Репозитории и сервис

### `ClientRepository.list_recent_by_master(master_id, limit=10) -> list[Client]`

```sql
SELECT c.*
FROM clients c
LEFT JOIN appointments a
  ON a.client_id = c.id AND a.master_id = :master_id
WHERE c.master_id = :master_id
GROUP BY c.id
ORDER BY MAX(a.start_at) DESC NULLS LAST, c.created_at DESC
LIMIT :limit
```

### `ClientRepository.search_by_master(master_id, query, limit=10) -> list[Client]`

Нормализация: `query = query.strip()`. Если `len(query) < 2` → `[]`. `digits = re.sub(r"\D", "", query)`.

```sql
SELECT * FROM clients
WHERE master_id = :master_id
  AND (name ILIKE '%' || :query || '%'
       OR (:digits != '' AND regexp_replace(phone, '\D', '', 'g') LIKE '%' || :digits || '%'))
ORDER BY name
LIMIT :limit
```

### `BookingService.create_manual(master, client, service, start_at, comment=None)` — **уже есть**

Проверено в `src/services/booking.py`. Сигнатура: `client: Client` (не id), параметр `comment` (не `notes`). Статус `"confirmed"`, `source="master_manual"`. `IntegrityError` → `SlotAlreadyTaken`. Рабочие часы не валидируются. Ничего менять не надо.

### `BookingService.cancel_by_client(appointment_id, tg_id) -> tuple[Appointment, Client, Master, Service]` — новый

Тонкая обёртка над существующим `BookingService.cancel(appointment_id, cancelled_by="client")`. Нужна отдельно из-за проверки владельца по `tg_id` и из-за возврата join-данных для уведомления мастеру.

- Загружает `Appointment` + `Client`, `Master`, `Service` одним `select` с `selectinload`.
- Нет / `client.tg_id != tg_id` → `NotFound`.
- `status in ('cancelled', 'rejected', 'completed', 'no_show')` → `InvalidState`.
- Делегирует в `self.cancel(..., cancelled_by="client")`.
- Возвращает кортеж для хэндлера (он использует `master.tg_id`, `client.name`, `service.name`).

**Важно:** статус в модели — `'cancelled'` (британская орфография с двумя `l`), не `'canceled'`. Все ссылки в спеке/плане используют `cancelled`.

## Хэндлеры

### `src/handlers/master/add_manual.py`

- `cmd_add(/add)` → `list_recent_by_master` → `recent_clients_kb` → `PickingClient`.
- `cb_pick_recent(RecentClientCallback)` — `client_id == "new"` → `NewClientName`; `== "search"` → `SearchingClient`; UUID → сохранить в FSM → `PickingService` с `services_pick_kb`.
- `msg_search_query(SearchingClient)` → `search_by_master` → `search_results_kb`; empty → «Ничего не нашёл», state тот же.
- `msg_new_client_name(NewClientName)` → validate ≥2 символов → save → `NewClientPhone`.
- `msg_new_client_phone(NewClientPhone)` → `normalize_phone`; bad → text prompt, state тот же. `get_by_phone(master_id, phone)` → found → `phone_dup_kb`, save `pending_name`/`pending_phone` в FSM. Not found → `upsert_by_phone`, save `client_id` → `PickingService`.
- `cb_phone_dup(PhoneDupCallback)` — `use` → save existing client_id → `PickingService`; `retry` → clear pending, retry prompt.
- `cb_pick_service(ClientServicePick, PickingService)` → save `service_id` → render calendar → `PickingDate`.
- `cb_pick_date(CalendarCallback, PickingDate)` — `prev/next` → re-render; `pick` → `find_free_slots` → `slots_grid_with_custom` → `PickingSlot`.
- `cb_pick_slot(SlotCallback, PickingSlot)` → save `start_at` → `EnteringComment`.
- `cb_custom_time(CustomTimeCallback, PickingSlot)` → prompt ввода → `EnteringCustomTime`.
- `msg_custom_time(EnteringCustomTime)` → parse `ДД.ММ ЧЧ:ММ` или `ЧЧ:ММ`; past → reject; OK → save `start_at` → `EnteringComment`.
- `msg_comment(EnteringComment)` → `notes = text.strip()[:200]` → render confirmation card → `Confirming`.
- `cb_skip_comment(SkipCommentCallback, EnteringComment)` → `notes=None` → confirmation card → `Confirming`.
- `cb_confirm_save(Confirming)` → `create_manual(master=..., client=..., service=..., start_at=..., comment=notes)` — параметр сервиса называется `comment`; `SlotAlreadyTaken` → alert + `PickingSlot`; success → reply + notify client (если `tg_id`) + `state.clear()`.
- `cb_confirm_cancel(Confirming)` → reply + `state.clear()`.
- `cmd_cancel_any` (`/cancel`, любой state в `MasterAdd`) → `state.clear()`.

### `src/handlers/client/cancel.py`

- `cb_cancel(ApprovalCallback.filter(F.action == "cancel"))` → `cancel_by_client(appointment_id, callback.from_user.id)`. Success → `callback.answer("Запись отменена")` + `edit_message_reply_markup(None)` + `bot.send_message(master.tg_id, ...)`. `NotFound`/`InvalidState` → alert «Запись уже недоступна».

## Callback data

```python
# src/callback_data/master_add.py
class RecentClientCallback(CallbackData, prefix="mac"):
    client_id: str  # UUID, "new", или "search"

class PhoneDupCallback(CallbackData, prefix="mdp"):
    action: Literal["use", "retry"]
    client_id: UUID

class SkipCommentCallback(CallbackData, prefix="msc"):
    pass

class CustomTimeCallback(CallbackData, prefix="mct"):
    pass
```

```python
# src/callback_data/approval.py (изменение)
class ApprovalCallback(CallbackData, prefix="appr"):
    action: Literal["confirm", "reject", "history", "cancel"]  # +cancel
    appointment_id: UUID
```

## Клавиатуры

- `recent_clients_kb(clients)` — 1 клиент на ряд (`{name} · {phone}`), ряд `[🔍 Поиск]` `[➕ Новый]`.
- `search_results_kb(clients)` — аналогично + ряд `[⬅ Отмена поиска]`.
- `phone_dup_kb(client_id)` — `[Да, использовать]` `[Отмена — ввести другой]`.
- `services_pick_kb` — из Эпика 4, переиспользуем.
- `calendar_kb` — из Эпика 4, переиспользуем.
- `slots_grid_with_custom(slots, *, tz)` — 3-в-ряд HH:MM, финальный ряд `[➕ Нестандартное время]` `[⬅ Назад]`.
- `skip_comment_kb()` — `[⏭ Пропустить]`.
- `confirm_add_kb()` — `[✅ Сохранить]` `[❌ Отмена]`.
- `client_cancel_kb(appointment_id)` — `[❌ Отменить запись]`.

## Строки (ключи для `src/strings.py`)

### Мастерские (`/add`)

- `MANUAL_PICK_CLIENT` — «Выбери клиента или создай нового:»
- `MANUAL_NO_RECENT` — «Ещё нет клиентов. Нажми ➕ Новый.»
- `MANUAL_SEARCH_PROMPT` — «Введи 2+ символа (имя или телефон):»
- `MANUAL_SEARCH_EMPTY` — «Ничего не нашёл. Попробуй ещё.»
- `MANUAL_ASK_NAME` — «Имя клиента:»
- `MANUAL_NAME_BAD` — «Минимум 2 символа. Попробуй ещё.»
- `MANUAL_ASK_PHONE` — «Телефон клиента (+374XXXXXXXX):»
- `MANUAL_PHONE_BAD` — «Формат: +374XXXXXXXX. Попробуй ещё.»
- `MANUAL_PHONE_DUP` — «По этому номеру уже есть клиент „{name}". Использовать его?»
- `MANUAL_ASK_SERVICE` — «Выбери услугу:»
- `MANUAL_ASK_DATE` — «Выбери дату:»
- `MANUAL_ASK_SLOT` — «Выбери время или введи нестандартное:»
- `MANUAL_CUSTOM_PROMPT` — «Введи дату и время: ДД.ММ ЧЧ:ММ (или только ЧЧ:ММ для выбранной даты):»
- `MANUAL_CUSTOM_BAD` — «Неверный формат. Пример: 25.04 14:30»
- `MANUAL_CUSTOM_PAST` — «Нельзя в прошлое. Выбери другое время.»
- `MANUAL_ASK_COMMENT` — «Комментарий (или нажми ⏭ Пропустить):»
- `MANUAL_CONFIRM_CARD` — `"Подтверди запись:\n👤 {client}\n📞 {phone}\n💇 {service}\n📅 {date} {time}\n📝 {notes}"`
- `MANUAL_SAVED` — «✅ Запись сохранена.»
- `MANUAL_CANCELED` — «Отменено.»
- `MANUAL_SLOT_TAKEN` — «Этот слот только что занят. Выбери другой.»

### Клиентские уведомления

- `CLIENT_NOTIFY_MANUAL` — «Врач записал вас на {date} {time} — {service}.»
- `CLIENT_CANCEL_BUTTON` — «❌ Отменить запись»
- `CLIENT_CANCEL_DONE` — «Запись отменена.»
- `CLIENT_CANCEL_UNAVAILABLE` — «Запись уже недоступна.»

### Мастерские уведомления об отмене клиентом

- `MASTER_NOTIFY_CLIENT_CANCELED` — «Клиент {name} отменил запись: {date} {time} — {service}.»

**Армянский перевод всех новых ключей — последней задачей плана, одним проходом.**

## Тесты (TDD)

- `test_repositories_clients_epic5.py` — `list_recent_by_master` (ordering by last appt, fallback to created_at), `search_by_master` (name/phone substring, digits only, <2 chars = empty).
- `test_services_booking_epic5.py` — `cancel_by_client` happy, NotFound (wrong tg_id / отсутствует), InvalidState (уже cancelled). `create_manual` уже покрыт тестами Эпика 3 — не повторяем.
- `test_handlers_master_add.py` — full FSM happy path (existing client), new client happy, phone dup «use», phone dup «retry», custom time path, slot taken race, /cancel in middle.
- `test_handlers_client_cancel.py` — happy path with master notification, InvalidState (already canceled), wrong client tg_id.

Цели покрытия: services ≥90%, handlers ≥60% (проектная планка).

## Гиены качества

- `ruff check .`, `ruff format --check .`, `mypy src/ --strict` — чисто.
- `pytest` — все тесты зелёные.
- Миграция Alembic — **не требуется** (новые колонки не нужны, `Appointment.notes` уже есть из Эпика 1).

## Будущие эпики (за рамками Эпика 5)

- Полноценный «Перенести» для клиента (новый booking FSM с календарём мастера).
- Эпик 6: мастер-календарь `/today` `/tomorrow` `/week` `/calendar` `/client`.
- Эпик 7: напоминания.
- Эпик 8: i18n-полировка, финальный деплой.
