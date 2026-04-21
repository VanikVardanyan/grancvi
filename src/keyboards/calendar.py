from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.calendar import CalendarCallback
from src.strings import strings

DayLoad = Literal["off", "full", "tight", "free"]

MAX_MONTHS_AHEAD: int = 3

_EMOJI: dict[DayLoad, str] = {"free": "🟢", "tight": "🟡", "full": "🔴", "off": "⚫"}


def _classify(count: int) -> DayLoad:
    if count < 0:
        return "off"
    if count == 0:
        return "full"
    if count < 5:
        return "tight"
    return "free"


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def _shift_month(d: date, by: int) -> date:
    total = d.year * 12 + (d.month - 1) + by
    return date(total // 12, (total % 12) + 1, 1)


def _noop_button(text: str, year: int, month: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=CalendarCallback(action="noop", year=year, month=month, day=0).pack(),
    )


def calendar_keyboard(
    *,
    month: date,
    loads: dict[date, int],
    today: date,
) -> InlineKeyboardMarkup:
    """Render a month grid with emoji-coded availability.

    `loads` must contain an entry for every day of `month`; -1 encodes "off",
    0 = full, 1..4 = tight, ≥5 = free. Past days render as ⚫ without a pick callback.
    """
    year, month_num = month.year, month.month
    month_name = strings.MONTH_NAMES[month_num - 1]

    prev_shift = _shift_month(month, -1)
    next_shift = _shift_month(month, +1)
    can_prev = _months_between(today.replace(day=1), prev_shift) >= 0
    can_next = _months_between(today.replace(day=1), next_shift) <= MAX_MONTHS_AHEAD

    prev_btn: InlineKeyboardButton
    if can_prev:
        prev_btn = InlineKeyboardButton(
            text="«",
            callback_data=CalendarCallback(
                action="nav", year=prev_shift.year, month=prev_shift.month, day=0
            ).pack(),
        )
    else:
        prev_btn = _noop_button(" ", year, month_num)

    next_btn: InlineKeyboardButton
    if can_next:
        next_btn = InlineKeyboardButton(
            text="»",
            callback_data=CalendarCallback(
                action="nav", year=next_shift.year, month=next_shift.month, day=0
            ).pack(),
        )
    else:
        next_btn = _noop_button(" ", year, month_num)

    header = [
        prev_btn,
        _noop_button(f"{month_name} {year}", year, month_num),
        next_btn,
    ]

    weekday_row = [
        _noop_button(label, year, month_num) for label in strings.WEEKDAY_SHORT
    ]

    rows: list[list[InlineKeyboardButton]] = [header, weekday_row]
    _, days_in_month = monthrange(year, month_num)
    first_weekday = date(year, month_num, 1).weekday()

    cells: list[InlineKeyboardButton] = [
        _noop_button(" ", year, month_num) for _ in range(first_weekday)
    ]
    for day in range(1, days_in_month + 1):
        d = date(year, month_num, day)
        count = loads.get(d, -1)
        load = _classify(count)
        emoji = _EMOJI[load]
        label = f"{emoji}{day}"
        if d < today or load == "off":
            cells.append(_noop_button(label, year, month_num))
        else:
            cells.append(
                InlineKeyboardButton(
                    text=label,
                    callback_data=CalendarCallback(
                        action="pick", year=year, month=month_num, day=day
                    ).pack(),
                )
            )

    while len(cells) % 7 != 0:
        cells.append(_noop_button(" ", year, month_num))

    for i in range(0, len(cells), 7):
        rows.append(cells[i : i + 7])

    return InlineKeyboardMarkup(inline_keyboard=rows)
