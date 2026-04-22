from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class SettingsCallback(CallbackData, prefix="set"):
    section: Literal["services", "hours", "breaks", "language"]


class WorkHoursDay(CallbackData, prefix="wh"):
    action: Literal["pick", "day_off", "done"]
    day: str = ""  # "mon".."sun" for pick/day_off, empty for "done"


class LanguageCallback(CallbackData, prefix="lang"):
    lang: Literal["ru", "hy"]
