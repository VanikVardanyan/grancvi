from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.settings import (
    LanguageCallback,
    SettingsCallback,
    WorkHoursDay,
    WorkHoursHour,
)
from src.strings import strings

_START_HOUR_MIN: int = 7
_START_HOUR_MAX: int = 21
_END_HOUR_MIN: int = 8
_END_HOUR_MAX: int = 23
_HOURS_PER_ROW: int = 4


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_PROFILE,
                    callback_data=SettingsCallback(section="profile").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_SERVICES,
                    callback_data=SettingsCallback(section="services").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_WORK_HOURS,
                    callback_data=SettingsCallback(section="hours").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_BREAKS,
                    callback_data=SettingsCallback(section="breaks").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_LANGUAGE,
                    callback_data=SettingsCallback(section="language").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_MY_INVITES,
                    callback_data=SettingsCallback(section="my_invites").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_NEW_INVITE,
                    callback_data=SettingsCallback(section="new_invite").pack(),
                )
            ],
        ]
    )


def _format_day_label(day_code: str, work_hours: dict[str, Any]) -> str:
    label = strings.WEEKDAYS[day_code]
    intervals = work_hours.get(day_code)
    if not intervals:
        return f"{label}: {strings.WORK_HOURS_DAY_OFF}"
    first = intervals[0]
    return f"{label}: {first[0]}-{first[1]}"


def work_hours_list(work_hours: dict[str, Any]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for code in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_format_day_label(code, work_hours),
                    callback_data=WorkHoursDay(action="pick", day=code).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.WORK_HOURS_BTN_DONE,
                callback_data=WorkHoursDay(action="done").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def language_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Русский",
                    callback_data=LanguageCallback(lang="ru").pack(),
                ),
                InlineKeyboardButton(
                    text="Հայերեն",
                    callback_data=LanguageCallback(lang="hy").pack(),
                ),
            ],
        ]
    )


def _hour_grid_rows(
    *, day: str, phase: str, hours: range, start_hour: int = 0
) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    buf: list[InlineKeyboardButton] = []
    for h in hours:
        buf.append(
            InlineKeyboardButton(
                text=f"{h:02d}:00",
                callback_data=WorkHoursHour(
                    day=day,
                    phase="start" if phase == "start" else "end",
                    hour=h,
                    start_hour=start_hour,
                ).pack(),
            )
        )
        if len(buf) == _HOURS_PER_ROW:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)
    return rows


def work_hours_start_picker(day: str) -> InlineKeyboardMarkup:
    rows = _hour_grid_rows(
        day=day, phase="start", hours=range(_START_HOUR_MIN, _START_HOUR_MAX + 1)
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.WORK_HOURS_BTN_DAY_OFF,
                callback_data=WorkHoursDay(action="day_off", day=day).pack(),
            ),
            InlineKeyboardButton(
                text=strings.WORK_HOURS_BTN_BACK,
                callback_data=WorkHoursDay(action="back", day=day).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def work_hours_end_picker(day: str, start_hour: int) -> InlineKeyboardMarkup:
    lower = max(start_hour + 1, _END_HOUR_MIN)
    rows = _hour_grid_rows(
        day=day, phase="end", hours=range(lower, _END_HOUR_MAX + 1), start_hour=start_hour
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.WORK_HOURS_BTN_BACK,
                callback_data=WorkHoursDay(action="back", day=day).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
