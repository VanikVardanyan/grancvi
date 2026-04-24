# Epic 4 — Клиентская запись (FSM + календарь + уведомления мастеру)

**Дата:** 2026-04-21
**Статус:** спека согласована, готово к плану
**Связанный эпик в BACKLOG.md:** 4 (задачи 4.1, 4.2, 4.3; `alt_time` из 4.3 перенесён в v0.2)

---

## 1. Scope и архитектура

**Что строим:** полный клиентский путь записи от `/start` до `pending`-заявки + уведомление мастеру + обработка решения мастера (confirm/reject/history).

**Что вне scope этого эпика:**
- `alt_time` (предложить другое время) — переезжает в v0.2, т.к. усложняет FSM мастера и требует отдельной ветки коммуникации.
- Multi-tenant / `/start m_{short_id}` — в v0.1 мастер один, DB содержит ровно одну запись `masters`; `/start` без параметра находит её напрямую. `short_id` не добавляется в модель до v0.2 (см. SPEC.md:492).
- Напоминания (24ч/2ч) — Epic 7.
- Мастерская ручная запись `/add` — Epic 5.

**Положение в слоях:**
- `handlers/client_booking.py` — новый: FSM-хэндлеры клиента.
- `handlers/master_approval.py` — новый: callback-хэндлеры на кнопках мастера.
- `keyboards/calendar.py` — новый: inline-календарь с загрузкой.
- `keyboards/slots.py` — новый: сетка свободных слотов.
- `fsm/client_booking.py` — новый: `ClientBooking` StatesGroup.
- `callback_data/calendar.py`, `callback_data/slots.py`, `callback_data/approval.py`, `callback_data/services.py` — новые: typed callback data (`CalendarCallback`, `SlotCallback`, `ApprovalCallback`, `ServiceCallback`).
- `repositories/clients.py` — новый: `ClientRepository.upsert_by_phone`, `get`.
- `repositories/masters.py` — дополнить: `get_singleton() -> Master | None` (v0.1-инвариант: ровно один мастер в БД).
- `repositories/appointments.py` — дополнить: `list_for_client`, `list_active_for_month`.
- `services/availability.py` — дополнить: `calculate_day_loads` (счётчик свободных слотов по каждому дню месяца).
- `services/booking.py` — дополнить: `get_month_load`, `list_client_history`.
- `utils/phone.py` — новый: `normalize(raw) -> str`, валидация армянского формата.

Слоистость из CLAUDE.md соблюдается: handler тонкий → service несёт логику → repository трогает БД.

---

## 2. Inline-календарь с раскраской по загрузке (Task 4.1)

### Данные
`BookingService.get_month_load(master, service, month: date, now)` возвращает `dict[date, DayLoad]`, где `DayLoad` — literal-like:
- `"off"` — рабочий график пуст на этот weekday, или день в прошлом.
- `"full"` — 0 свободных слотов.
- `"tight"` — 1..4 свободных слота.
- `"free"` — ≥5 свободных слотов.

Внутри:
1. Запросить `AppointmentRepository.list_active_for_month(master_id, month_start_utc, month_end_utc)` — все активные записи на месяц одним запросом.
2. Сгруппировать в dict[date, list[(start, end)]] в `master.timezone`.
3. Для каждого дня месяца вызвать `availability.calculate_day_loads`, получить число свободных слотов, сконвертировать в DayLoad.

### Чистая функция
```python
def calculate_day_loads(
    *, work_hours, breaks, booked_by_day: dict[date, list[tuple[datetime, datetime]]],
    month: date, tz: ZoneInfo, slot_step_min: int, service_duration_min: int, now: datetime,
) -> dict[date, int]:
    """Для каждого дня месяца вернуть число свободных слотов (-1 если нерабочий)."""
```
Реализация — цикл по дням месяца + делегация существующему `calculate_free_slots`. Единственный новый код — обход дат и упаковка результата.

### Клавиатура
`keyboards/calendar.py::calendar_keyboard(month: date, loads: dict[date, DayLoad], today: date) -> InlineKeyboardMarkup`:
- Шапка: `« Апрель 2026 »` (callback prev/next, disabled если выходит из допустимого окна [today_month, today_month+3]).
- Неделя: `Пн Вт Ср Чт Пт Сб Вс`.
- Ячейки: `emoji + DD`. Раскраска: 🟢 free, 🟡 tight, 🔴 full, ⚫ off/past.
- Пустые ячейки до первого понедельника месяца — кнопки с `callback_data="noop"`.
- Callback на дату: `CalendarCallback(action="pick", date="2026-04-21")`.

### Callback data
```python
class CalendarCallback(CallbackData, prefix="cal"):
    action: Literal["pick", "nav", "noop"]
    year: int
    month: int
    day: int = 0  # 0 для навигации
```

### Тесты
- `availability.calculate_day_loads`: таблично — пустой месяц, день без work_hours, сегодня после полудня (часть слотов отсечена по `now`), полная занятость, смешанная.
- `keyboards.calendar_keyboard`: структурно — shape клавиатуры (7 колонок, правильный эмодзи, отключённая навигация на границах окна).

---

## 3. Клиентский FSM (Task 4.2)

### Состояния
```python
class ClientBooking(StatesGroup):
    ChoosingService = State()
    ChoosingDate = State()
    ChoosingTime = State()
    EnteringName = State()
    EnteringPhone = State()
    Confirming = State()
```

### Поток
1. `/start` → клиентский хэндлер срабатывает, когда `data["master"] is None` (middleware уже попыталась резолвить по `tg_id`, это клиент, не мастер). Хэндлер зовёт `MasterRepository.get_singleton()` — в v0.1 это единственный мастер. Если `None` — сообщение «бот не настроен, свяжитесь с мастером» и выход. Иначе — `ChoosingService`: список активных услуг через `ServiceRepository.list_active(master.id)`. Inline-кнопки с `ServiceCallback(service_id)`.
2. `ChoosingService` → callback с `service_id`. Сохраняем `service_id` в FSM context. Переход в `ChoosingDate` с календарём на текущий месяц.
3. `ChoosingDate` → `CalendarCallback("pick", ...)`. Сохраняем `date`. Запрашиваем `BookingService.get_free_slots`, рендерим `slots_grid`. Если список пуст — сообщение «На этот день слотов нет» + календарь заново.
4. `ChoosingTime` → `SlotCallback(hh, mm)`. Сохраняем `start_at_utc` в FSM. Переход в `EnteringName` с текстом «Как вас зовут?».
5. `EnteringName` → текст. Валидация: `1 <= len(trim) <= 60`. При провале — вежливое сообщение с просьбой повторить. При успехе — `EnteringPhone` с просьбой «Телефон в формате +374 XX XXX XXX».
6. `EnteringPhone` → текст. `utils.phone.normalize` → при провале сообщение об ошибке формата + retry. При успехе — `Confirming` с summary-сообщением:
   > 📋 Проверьте запись:\n🧑‍⚕️ Услуга: {service.name}\n📅 {dd.mm, HH:MM}\n👤 {name}\n📞 {phone}\n\nПодтвердить?
   Inline-кнопки «✅ Подтвердить» / «❌ Отменить».
7. `Confirming` → confirm callback:
   - `ClientRepository.upsert_by_phone(master_id, phone, name, tg_id)` — возвращает `Client`.
   - `BookingService.create_pending(master=..., client=..., service=..., start_at=...)` → `Appointment`.
   - На `SlotAlreadyTaken` — сообщение «Слот уже занят» + возврат в `ChoosingTime` с обновлённой сеткой.
   - На успех — сообщение клиенту «Заявка отправлена мастеру, ожидайте подтверждения» + отправка уведомления мастеру (см. секцию 4). FSM очистить.
8. Отмена на любом шаге — кнопка «❌ Отменить» или команда `/cancel` → FSM clear + «Запись отменена».

### FSM data
В `state.data` хранить минимум: `service_id: str (UUID)`, `date: str (iso)`, `start_at: str (iso UTC)`, `name: str`, `phone: str`. Модели целиком не держим.

### Идемпотентность
- Повторный `/start` на любом шаге — сбросить FSM, начать заново.
- Двойной клик по кнопке подтверждения — второй клик получит `SlotAlreadyTaken` или, если первый ещё не прошёл, обычно ничего страшного: в БД partial unique index защитит.

### Тесты (aiogram test patterns)
- Happy-path: `/start` → service → date → time → name → phone → confirm. Проверить: `create_pending` вызван с правильными аргументами, клиент получил финальное сообщение.
- Race: на confirm `create_pending` кидает `SlotAlreadyTaken` → бот рендерит обновлённую сетку, FSM в `ChoosingTime`.
- Валидации: пустое имя → retry; невалидный телефон → retry.
- `/cancel` на каждом шаге — FSM очищен.

---

## 4. Мастерская сторона — уведомление и решение (Task 4.3)

### Уведомление при `create_pending`
В клиентском хэндлере после успешного `create_pending`:
```
🔔 Новая заявка
🧑 {client.name}
📞 {client.phone}
🧑‍⚕️ {service.name} ({service.duration_min} мин)
📅 {dd.mm.yyyy, HH:MM} ({day_of_week})

[✅ Подтвердить] [❌ Отклонить]
[📋 История клиента]
```
Callback data — `ApprovalCallback(action, appointment_id)`.

### Handler pattern
`handlers/master_approval.py`:
- `cb_confirm` → `BookingService.confirm(appointment_id, master_id)`:
  - `NotFound` (appointment стёрт, чего не бывает в v0.1) → `callback.answer("Не найдено", show_alert=True)`.
  - `InvalidState` → `callback.answer("Уже обработано", show_alert=True)` + `edit_reply_markup(None)` чтобы снять кнопки.
  - Success → `edit_text` оригинального сообщения с пометкой `✅ Подтверждено в HH:MM` + `reply_markup=None`. Клиенту — `bot.send_message(client.tg_id, "Мастер подтвердил вашу запись...")` если `client.tg_id is not None`.
- `cb_reject` → аналогично, но вызывает `BookingService.reject(appointment_id, master_id)`. Причину в v0.1 не запрашиваем (reason=None).
- `cb_history` → `BookingService.list_client_history(master, client_id, limit=10)` → собираем в текст:
  ```
  История клиента {name} (последние 10):
  • 12.03.2026 14:00 — Маникюр — ✅ confirmed
  • 05.02.2026 11:30 — Стрижка — ❌ cancelled (by client)
  ...
  ```
  Отправляем `callback.answer(text, show_alert=True)` — т.к. Telegram лимит 200 символов на alert, при превышении переключаемся на `bot.send_message(master.tg_id, text)` + `callback.answer()` без alert.

### Новые методы
- `AppointmentRepository.list_for_client(master_id, client_id, limit=10, exclude_statuses=("pending",)) -> list[Appointment]` — ORDER BY `start_at DESC`.
- `BookingService.list_client_history(master, client_id, limit=10) -> list[Appointment]` — тонкая делегация.

### Строки (locales/ru/LC_MESSAGES/bot.ftl добавки)
- `appt-notify-master-new` — шаблон уведомления.
- `appt-notify-client-confirmed`, `appt-notify-client-rejected` — текст клиенту.
- `appt-button-confirm`, `appt-button-reject`, `appt-button-history` — названия кнопок.
- `appt-already-processed` — alert на двойной клик.
- `appt-confirmed-stamp` — «✅ Подтверждено в {time}».
- `appt-history-line` — строка истории клиента.

### Edge cases
- Клиент без `tg_id` (создан мастером вручную в будущих эпиках) — `bot.send_message` пропускается, никаких ошибок.
- Клиент заблокировал бота — `TelegramForbiddenError` ловим и логируем без паники (мастер уже увидел, что записалось).
- Мастер нажал на кнопку в старой заявке, которая уже обработана — `InvalidState` ветка.
- Скоупинг по `master_id` — `BookingService.confirm/reject` уже валидирует, что appointment принадлежит этому мастеру.

### Тесты
- Repo: `list_for_client` — сортировка DESC, лимит, исключение статусов.
- Service: `list_client_history` — 1 тест на делегацию.
- Handler: `cb_confirm` happy-path, `cb_confirm` на уже-подтверждённую (`InvalidState`), `cb_reject` happy-path, `cb_history` с короткой историей, `cb_history` с длинной историей (fallback на `send_message`).

---

## 5. Стратегия тестирования

### Pure (100% покрытия)
- `availability.calculate_day_loads` — таблично, как `calculate_free_slots` в Epic 3.
- `utils.phone.normalize` — parametrize: корректные варианты (`+374 99 123 456`, `+37499123456`, `099 12 34 56`), неверные (латиница, неверная длина, не-армянский код).

### Repositories (интеграционные, реальная PG через `session` fixture)
- `ClientRepository.upsert_by_phone` — insert, update, уникальность `(master_id, phone)`.
- `AppointmentRepository.list_for_client` — сортировка, лимит, exclude statuses.
- `AppointmentRepository.list_active_for_month` — диапазон, только активные.

### Services
- `BookingService.get_month_load` — склейка repo + pure, tz-границы, «сегодня» отсекает прошлые слоты.
- `BookingService.list_client_history` — 1 теста достаточно.

### Handlers (aiogram test patterns, ≥60%)
- Client happy-path (один длинный сценарий), client race (SlotAlreadyTaken на confirm), client валидации (имя, телефон), `/cancel`.
- Master approve confirm/reject, master двойной клик (InvalidState), master history (короткая/длинная).

### Keyboards (shape, не взаимодействие)
- `calendar_keyboard` — 7 колонок, раскраска, навигация на границах окна.
- `slots_grid` — формат HH:MM, 3 в строке.

### Не тестируем
- aiogram framework (`CallbackData.pack/unpack`, RedisStorage).
- i18n Fluent (пока RU-only через ContextVar, переключатель появится в Epic 8).

### Цели
- ~30–40 новых тестов поверх 82 существующих.
- `availability.py` 100%, `booking.py` ≥95%, `repositories/*` ≥90%, handlers ≥60%.
- Без моков БД — дисциплина из Epic 2/3, `session` fixture.

---

## 6. Открытые вопросы на план

- Куда положить `DayLoad` Literal — прямо в `availability.py` или в `services/booking.py`? Решим на этапе плана, тяготеет к `availability.py` вместе с `calculate_day_loads`.
- Как именно обрезать историю клиента при длине > 200 симв на alert — решим в задаче 4.3 в плане, варианты известны.
- Нужно ли `utils/phone.py` проверять только армянский код или допускать любой `+код`? V0.1 = Армения, значит только `+374`. Иные форматы → ошибка валидации.

Все перечисленные вопросы не блокируют дизайн — решаются на уровне плана/реализации.
