# ruff: noqa: RUF001
from __future__ import annotations

from datetime import date

from src.callback_data.calendar import CalendarCallback
from src.keyboards.calendar import MAX_MONTHS_AHEAD, calendar_keyboard


def _all_buttons(kb) -> list:
    return [b for row in kb.inline_keyboard for b in row]


def _days(kb) -> list:
    return [b for b in _all_buttons(kb) if len(b.text) >= 1 and b.text[0] in "🟢🟡🔴⚫"]


def test_header_row_has_month_and_year() -> None:
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): -1 for d in range(1, 32)},
        today=date(2026, 4, 21),
    )
    header = kb.inline_keyboard[0]
    assert len(header) == 3
    assert "Май 2026" in header[1].text


def test_weekday_header_row() -> None:
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): -1 for d in range(1, 32)},
        today=date(2026, 4, 21),
    )
    weekday_row = kb.inline_keyboard[1]
    labels = [b.text for b in weekday_row]
    assert labels == ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def test_day_cells_use_correct_emoji() -> None:
    loads = {date(2026, 5, d): -1 for d in range(1, 32)}
    loads[date(2026, 5, 4)] = 9
    loads[date(2026, 5, 5)] = 3
    loads[date(2026, 5, 6)] = 0
    loads[date(2026, 5, 7)] = -1

    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads=loads,
        today=date(2026, 4, 21),
    )
    day_texts = {b.text for b in _days(kb)}
    assert any(t.startswith("🟢") and t.endswith("4") for t in day_texts)
    assert any(t.startswith("🟡") and t.endswith("5") for t in day_texts)
    assert any(t.startswith("🔴") and t.endswith("6") for t in day_texts)
    assert any(t.startswith("⚫") for t in day_texts)


def test_day_callback_packs_pick_action() -> None:
    loads = {date(2026, 5, d): 9 for d in range(1, 32)}
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads=loads,
        today=date(2026, 4, 21),
    )
    picked = next(
        b for b in _all_buttons(kb) if b.callback_data and b.callback_data.startswith("cal:pick")
    )
    restored = CalendarCallback.unpack(picked.callback_data)
    assert restored.action == "pick"
    assert restored.year == 2026
    assert restored.month == 5


def test_past_day_cells_are_noop() -> None:
    loads = {date(2026, 5, d): -1 for d in range(1, 32)}
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads=loads,
        today=date(2026, 5, 15),
    )
    for b in _days(kb):
        if b.callback_data and b.callback_data.startswith("cal:pick"):
            cb = CalendarCallback.unpack(b.callback_data)
            assert cb.day >= 15


def test_prev_disabled_when_at_current_month() -> None:
    loads = {date(2026, 5, d): -1 for d in range(1, 32)}
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads=loads,
        today=date(2026, 5, 21),
    )
    prev = kb.inline_keyboard[0][0]
    assert CalendarCallback.unpack(prev.callback_data).action == "noop"


def test_next_disabled_at_max_lookahead() -> None:
    target_month = date(2026, 5, 1)
    today = date(2026, 5, 1)
    far = date(
        target_month.year + (target_month.month + MAX_MONTHS_AHEAD - 1) // 12,
        ((target_month.month + MAX_MONTHS_AHEAD - 1) % 12) + 1,
        1,
    )
    loads = {date(far.year, far.month, d): -1 for d in range(1, 29)}
    kb = calendar_keyboard(month=far, loads=loads, today=today)
    nxt = kb.inline_keyboard[0][2]
    assert CalendarCallback.unpack(nxt.callback_data).action == "noop"
