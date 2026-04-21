from __future__ import annotations

from datetime import date

from src.callback_data.calendar import CalendarCallback
from src.keyboards.calendar import calendar_keyboard


def _collect_callbacks(kb: object) -> list[str]:
    out: list[str] = []
    rows = getattr(kb, "inline_keyboard", [])
    for row in rows:
        for btn in row:
            cd = getattr(btn, "callback_data", None)
            if cd is not None:
                out.append(str(cd))
    return out


def test_default_blocks_prev_from_current_month() -> None:
    today = date(2026, 5, 10)
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): 5 for d in range(1, 32)},
        today=today,
    )
    # Prev button renders as noop when at current month boundary (existing behaviour).
    packed = _collect_callbacks(kb)
    prev_nav = [p for p in packed if p.startswith("cal:nav") and ":4:" in p]
    assert prev_nav == []


def test_allow_past_enables_prev_nav_into_prior_months() -> None:
    today = date(2026, 5, 10)
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): 5 for d in range(1, 32)},
        today=today,
        allow_past=True,
    )
    packed = _collect_callbacks(kb)
    # Expect a nav callback for previous month (April 2026).
    assert any(CalendarCallback(action="nav", year=2026, month=4).pack() == p for p in packed)


def test_allow_past_makes_past_days_clickable() -> None:
    today = date(2026, 5, 10)
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): 5 for d in range(1, 32)},
        today=today,
        allow_past=True,
    )
    packed = _collect_callbacks(kb)
    # Day 3 is in the past; should render as pick, not noop.
    pick = CalendarCallback(action="pick", year=2026, month=5, day=3).pack()
    assert pick in packed
    # Noop cells carry day=0; past day with allow_past should NOT be represented as noop.
    # (Other noop cells still exist for empty grid slots — we only check 'pick' exists.)


def test_default_past_days_remain_noop() -> None:
    today = date(2026, 5, 10)
    kb = calendar_keyboard(
        month=date(2026, 5, 1),
        loads={date(2026, 5, d): 5 for d in range(1, 32)},
        today=today,
    )
    packed = _collect_callbacks(kb)
    # Day 3 (past) should NOT be clickable under default behaviour.
    pick = CalendarCallback(action="pick", year=2026, month=5, day=3).pack()
    assert pick not in packed
