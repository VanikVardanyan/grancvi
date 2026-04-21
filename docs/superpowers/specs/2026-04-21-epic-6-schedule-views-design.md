# Epic 6 — Schedule Views Design

**Status:** Approved (2026-04-21). Ready for implementation planning.

**Goal:** Give the master three read-oriented schedule surfaces — `/today`/`/tomorrow`, `/week`+`/calendar`, `/client` — plus the ability to close out past `confirmed` appointments (mark them `completed` or `no_show`) and edit client notes. Data already exists from Epics 3–5; Epic 6 adds handlers, a shared day-schedule renderer, and a handful of repo/service extensions.

---

## Scope

BACKLOG.md tasks 6.1–6.3:

- **6.1** — `/today`, `/tomorrow`: list of the day's appointments + free slots inside work hours + inline navigation.
- **6.2** — `/week`, `/calendar`: 7-day snapshot with load bar; inline calendar month with nav forward/back; clicking any day renders that day's schedule; past-day schedules expose buttons to mark still-`confirmed` appointments as `completed` / `no_show`.
- **6.3** — `/client`: search by name or phone; client page with notes and full appointment history; editable notes; bridge into `/add` with the client pre-selected.

Single master per bot (v0.1 architecture). All new surfaces are master-facing (gated by the existing master-router scheme).

---

## Architecture

### New handler modules (under `src/handlers/master/`)

| File | Responsibility |
| --- | --- |
| `today.py` | `/today`, `/tomorrow`, + callback re-renders for same-day navigation |
| `week.py` | `/week` snapshot + clicks into day schedule |
| `calendar.py` | `/calendar` (inline month nav, past months allowed) + clicks into day schedule |
| `client_page.py` | `/client` FSM search → pick → client page → edit notes → bridge to `/add` |
| `mark_past.py` | Single callback handler for "✅ Был" / "❌ Не пришёл" buttons that may appear in any day-schedule message |

### Shared rendering

New module `src/utils/schedule_format.py` is the **single source of truth for day-schedule output**. Every surface that shows one day (today/tomorrow/week-day-click/calendar-day-click) dispatches to the same renderer; the only difference is the navigation bar attached below.

Public API (all synchronous, pure):

```python
def render_day_schedule(
    *,
    d: date,
    appts: list[Appointment],      # already loaded by handler
    work_hours: dict,
    breaks: dict,
    tz: ZoneInfo,
    slot_step_min: int,
    now: datetime,                 # for past/future split
    day_nav: list[list[InlineKeyboardButton]],  # passed in by caller
) -> tuple[str, InlineKeyboardMarkup]:
    """Assemble text + keyboard for one day's schedule."""
```

Text layout (separate sections, per user choice):

```
📅 {Weekday} {DD} {mon}
🕐 Рабочие часы: HH:MM–HH:MM        ← or "выходной"

📋 Записи (N):
{status_emoji} HH:MM  {client_name} · {service_name}
...

🆓 Свободно:
HH:MM, HH:MM, HH:MM, ...             ← or absent if day off / no gaps
```

Status emoji mapping:
- `✅` — `confirmed` or `completed`
- `⏳` — `pending`
- `❌` — `no_show`
- `cancelled` and `rejected` are **not shown** (out of scope for daily view).

Free slots are computed from the master's `slot_step_min` grid intersected with `work_hours` minus `breaks` minus every booked appointment's `[start_at, start_at+duration_min)` interval. Service-agnostic: we show every grid point that is currently unbooked, regardless of any specific service duration.

### New callback data (under `src/callback_data/`)

| File | Class | Fields |
| --- | --- | --- |
| `schedule.py` | `DayPickCallback` | `ymd: str` (ISO `YYYY-MM-DD`) |
| `schedule.py` | `DayNavCallback` | `action: Literal["today","tomorrow","week","calendar"]` |
| `mark_past.py` | `MarkPastCallback` | `action: Literal["present","no_show"]`, `appointment_id: UUID` |
| `master_calendar.py` | `MasterCalendarCallback` | `action: Literal["pick","nav","noop"]`, `year: int`, `month: int`, `day: int` (prefix `mca` — distinct from client's `cal`) |
| `client_page.py` | `ClientPickCallback` | `client_id: UUID` |
| `client_page.py` | `ClientNotesEditCallback` | `client_id: UUID` |
| `client_page.py` | `ClientAddApptCallback` | `client_id: UUID` |

All typed aiogram `CallbackData`, no string-format payloads. Each one fits into the 64-byte Telegram limit.

### FSM

New `src/fsm/master_view.py::MasterView` with two states:

- `SearchingClient` — after `/client`, awaiting a text query.
- `EditingNotes` — after clicking "✏️ Редактировать заметки" on a client page, awaiting the new notes text. FSM data holds `client_id`.

No states for `/today`, `/week`, `/calendar`, `/client`-page itself — these are stateless read views.

### Data layer extensions

**`AppointmentRepository`:**

```python
async def list_for_master_range(
    self,
    master_id: UUID,
    *,
    start_utc: datetime,
    end_utc: datetime,
    statuses: tuple[str, ...] | None = None,  # None → default active set
) -> list[Appointment]:
    """General range query. Default statuses filter excludes cancelled/rejected."""
```

Supersedes the narrower `list_active_for_day` and `list_active_for_month` in intent, but those stay — they're still used by Epics 3–4. New code uses the range method.

**`ClientRepository`:**

```python
async def update_notes(self, client_id: UUID, notes: str | None) -> None:
    """Set `Client.notes`. Empty string or None → clears the field (stored as NULL)."""
```

**`BookingService`:**

```python
async def mark_completed(
    self,
    appointment_id: UUID,
    *,
    master: Master,
    now: datetime | None = None,
) -> Appointment:
    """Promote a confirmed, already-ended appointment to `completed`.

    Raises NotFound if absent or owned by another master.
    Raises InvalidState if status != 'confirmed' or end_at > now.
    """

async def mark_no_show(
    self,
    appointment_id: UUID,
    *,
    master: Master,
    now: datetime | None = None,
) -> Appointment:
    """Same preconditions as mark_completed; sets status='no_show'."""
```

`list_client_history(client_id)` gains a `*, limit: int = 10` parameter (current fixed-cap is likely 10; the client page wants 20).

### Handler DI

All handlers receive `session: AsyncSession`, `master: Master` (required — master router is gated by `_IsMasterOrAdmin`), `state: FSMContext`, `bot: Bot` (for callbacks that send new messages). Same convention as Epic 5 `add_manual.py`.

### Router registration

Append to `src/handlers/master/__init__.py`:

```python
router.include_router(today_router)
router.include_router(week_router)
router.include_router(calendar_router)
router.include_router(client_page_router)
router.include_router(mark_past_router)
```

Order after `add_manual_router`.

---

## Feature details

### `/today` and `/tomorrow`

- Single handler (`cmd_today_or_tomorrow`) parametrized by date offset (0 or 1).
- Computes `d = now_in_master_tz().date() + offset`.
- Loads appts via `list_for_master_range(start_of_day_utc, end_of_day_utc)`, default active statuses.
- Calls `render_day_schedule(...)`; day-nav keyboard differs:
  - `/today`: `[📅 Завтра]` `[🗓 Неделя]` `[➕ Добавить]`
  - `/tomorrow`: `[⬅ Сегодня]` `[🗓 Неделя]` `[➕ Добавить]`
- **Mark-past buttons** are part of `render_day_schedule`'s keyboard, not the nav bar. Appended after the nav row. They appear for every appt where `status == 'confirmed'` AND `end_at < now`. Layout: one row per appt with two buttons `[✅ {HH:MM} {short_name}]` `[❌ {HH:MM} {short_name}]`. `short_name` is first 12 chars of the client name (callback payload is the appointment UUID — no names in payload).
- Tapping a mark button → handler in `mark_past.py` calls `mark_completed` / `mark_no_show` → re-renders the whole day schedule in-place (`edit_text` / `edit_reply_markup`). If edit fails with "message is not modified" it's swallowed; any other telegram error is logged but doesn't raise to the user.
- `[📅 Завтра]` / `[⬅ Сегодня]` / `[🗓 Неделя]` callbacks edit the current message to the new view (no extra messages).
- `[➕ Добавить]` callback: clears FSM, enters `MasterAdd.PickingClient`, sends new message with `recent_clients_kb(...)` (same as typing `/add`).

### `/week`

- Computes 7 days starting today (master tz).
- Single range query: `list_for_master_range(start_utc, start_utc + 7d)`. Groups in Python by local date.
- Per day: `N appts` (count with default statuses), `booked_min` (sum of `duration_min`), `work_min` (from `work_hours` minus `breaks` for that weekday; 0 if day off).
- Bar: 8 chars, `filled = round(booked_min / work_min * 8)` clamped to [0, 8]. Day off → "выходной" in place of percent, 8 `░`.
- Text:

```
🗓 Неделя с {DD mon}

{wd} {DD.MM}  {N} зап  {bar}  {pct}%     ← or "выходной"
{wd} {DD.MM}  ...
```

- Inline keyboard:
  - Rows of 3 day buttons (3+3+1 for 7): `[{wd} {DD}]` with `DayPickCallback(ymd="2026-04-24")`.
  - Bottom row: `[⬅ Сегодня]` `[🗓 Календарь]`.
- Click on a day button → send new message with `render_day_schedule(...)` for that date (nav bar for arbitrary day: `[⬅ Назад в неделю]` `[🗓 Календарь]`).
- No prev/next-week buttons — `/calendar` is the navigator.

### `/calendar`

- Shows current month in `master.timezone`.
- Reuses `src/keyboards/calendar.py::calendar_keyboard`. **Patch needed:** check whether the existing keyboard restricts navigation to current/future months. If yes, add an `allow_past: bool = False` parameter (client keeps current behavior; master passes `True`).
- Day cells colored by load (already implemented, from Epic 4's `get_month_load`).
- Uses `MasterCalendarCallback` (prefix `mca`) so the client's `CalendarCallback` (prefix `cal`) is untouched and there's no cross-fire between flows.
- `action="nav"` with year/month → re-render calendar for that month (edit_text).
- `action="pick"` with year/month/day → send new message with `render_day_schedule(...)` for that date. Nav bar on that day message: `[⬅ Назад в календарь]`.
- `action="noop"` → silent `answer()`.

### `/client`

**Search:**

1. `/client` → bot prompts "Имя или телефон клиента:" → `MasterView.SearchingClient`.
2. User types query:
   - len < 2 → reprompt, stay in state.
   - Call `ClientRepository.search_by_master(master_id, q)` (already exists from Epic 5).
   - 0 results → "Никого не нашёл. Попробуй ещё." — stay in state.
   - 1 result → jump to client page (step 3).
   - ≥2 results → inline-keyboard list, one row per client (`[{name} {phone}]` with `ClientPickCallback(client_id)`). Stay in state so user can re-search.
3. Click on picker row → client page, clear state.

**Client page:**

Text (rendered by a separate helper in `schedule_format.py` or a small inline helper in `client_page.py`):

```
👤 {client.name}
📞 {client.phone}

📝 Заметки:
{client.notes or "_не указано_"}

📊 История ({count} записей):
{status_emoji} {DD.MM}  {HH:MM}  {service_name}{maybe_" · будущая"}
...
{"и ещё N" if truncated}
```

- Sort `start_at DESC`, limit 20.
- Status emoji:
  - `completed` → `✅`
  - `pending` or (`confirmed` with `start_at > now`) → `⏳`, plus ` · будущая` suffix for future ones
  - `confirmed` with `start_at <= now` (past, not yet closed) → `⏳`
  - `no_show` → `❌`
  - `cancelled` → `❌`, suffix ` · отменена`
  - `rejected` → `❌`, suffix ` · отклонена`
- Inline keyboard:
  - `[✏️ Редактировать заметки]` → `ClientNotesEditCallback(client_id)`
  - `[➕ Добавить запись]` → `ClientAddApptCallback(client_id)`

**Edit notes:**

1. `ClientNotesEditCallback` → state `MasterView.EditingNotes`, FSM data: `{"client_id": "..."}`. Prompt: "Новые заметки (или отправь `-` чтобы очистить):".
2. User types:
   - `-` or empty-after-strip → `update_notes(client_id, None)`.
   - Otherwise `update_notes(client_id, text[:500])` (hard cap 500 chars; longer is trimmed).
3. Reply: "Сохранено." + re-render client page.
4. Clear state.

**Bridge to `/add`:**

1. `ClientAddApptCallback(client_id)` → clear current state, set `MasterAdd.PickingService`, put `{"client_id": str(client_id)}` into FSM data.
2. Load services, reply with services picker (same keyboard Epic 5 uses). User continues the Epic 5 flow from there.

---

## Error handling

- **Appointment not found / not yours:** `mark_completed`/`mark_no_show` raise `NotFound`; callback answers "Запись недоступна" alert, no message change.
- **Appointment already closed or still in the future:** raise `InvalidState`; alert "Ещё не закончилась" or "Уже помечена".
- **Edit-message failures:** "message is not modified" → swallowed silently. Other telegram errors logged at warn level, user sees no error (the action still succeeded in DB).
- **Client deleted mid-flow** (e.g., page open, someone deletes): `ClientPickCallback` → bot says "Клиент не найден" and returns to search prompt.
- **Past calendar months:** no errors, just render. Empty months render normally.

---

## Out of scope (explicit YAGNI)

- No CSV / PDF export.
- No history filters by service or date range.
- No bulk operations ("mark all past confirmed as completed").
- No prev/next-week buttons on `/week` — use `/calendar` for arbitrary dates.
- No highlighting of work-vs-off days on the calendar keyboard beyond existing load coloring.
- No deep-link from a chat mention of a phone number.
- No pagination beyond the 20-row history cap.

---

## Testing

Target: +~30 tests, suite at ~240 total.

| Test file | Covers |
| --- | --- |
| `test_utils_schedule_format.py` | Pure-function edge cases: day off, empty day, mixed statuses, past/future split, breaks carving |
| `test_repo_appointments_range.py` | `list_for_master_range` with/without status filter, boundary times |
| `test_repo_clients_notes.py` | `update_notes` set / clear |
| `test_services_booking_mark.py` | `mark_completed`, `mark_no_show` with wrong master, wrong status, future end_at |
| `test_handlers_master_today.py` | `/today`, `/tomorrow`, nav callbacks, mark-past buttons appear/disappear |
| `test_handlers_master_week.py` | 7-day snapshot layout, day-pick callback |
| `test_handlers_master_calendar.py` | Inline nav forward/back, past months allowed, day pick |
| `test_handlers_master_client_page.py` | Search flow (0/1/many), page render, notes edit, bridge to `/add` |

Pattern: `_FakeMsg` / `_FakeCb` dataclasses as in Epic 4/5 tests, `MemoryStorage` for FSM, real DB session fixture, `AsyncMock` for `Bot`.

Coverage goals (per CLAUDE.md):
- `utils/schedule_format.py` — ≥95% (pure).
- `services/booking.py` new methods — ≥95%.
- New handlers — ≥70%.

---

## Strings

~30 new keys in `src/strings.py`. Categories:

- `SCHED_*` — day header, section titles, weekday labels already exist, reuse.
- `WEEK_*` — week snapshot header, "выходной", bar-format template.
- `CLIENT_PAGE_*` — page header, notes prompts, history section, truncation suffix.
- `MARK_PAST_*` — button labels, success/error alerts.
- `DAY_NAV_*` — navigation button labels (`⬅ Сегодня`, `📅 Завтра`, `🗓 Неделя`, `🗓 Календарь`, `⬅ Назад в неделю`, `⬅ Назад в календарь`).

RU populated inline. HY mirrors RU in this epic; user delivers Armenian translations at the end (same workflow as Epic 5, Task 10).

---

## Risks and open items

- **Telegram message length:** `/week` (7-line snapshot) and `/today` with 10+ appts are well under 4096 bytes. `/client` page with 20 history rows + notes can be tight for very long names or notes. Mitigation: hard-cap notes display to 500 chars; trim history to 20.
- **Mark-past keyboard size:** at 8+ confirmed-past appointments in a single day the keyboard becomes long (2 buttons × N rows). Acceptable for v0.1 single-master; revisit if it bites.
- **`calendar_keyboard` past-month restriction:** will be checked at implementation start. If the keyboard hard-codes the restriction, patch adds a parameter; if it was already flexible, no patch.
- **Timezone edge at midnight:** the day boundary is `master.timezone` local midnight → converted to UTC before querying. Unit tests cover a non-UTC master (Asia/Yerevan).
- **Concurrency on mark-past:** two quick taps — the second one hits `InvalidState` (already closed) and shows alert. No race damage.

---

## Follow-up (Epic 7)

Reminders via APScheduler are Epic 7 per BACKLOG. Not touched here. The `mark_past` surface closes the loop so that stale `confirmed` appointments don't accumulate before reminders land.
