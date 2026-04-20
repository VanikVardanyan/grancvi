from __future__ import annotations

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.settings import SettingsCallback, WorkHoursDay
from src.strings import strings


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
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


def work_hours_day_prompt(day: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.WORK_HOURS_BTN_DAY_OFF,
                    callback_data=WorkHoursDay(action="day_off", day=day).pack(),
                )
            ]
        ]
    )
