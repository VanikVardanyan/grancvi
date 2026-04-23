from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class SettingsCallback(CallbackData, prefix="set"):
    section: Literal[
        "services", "hours", "breaks", "language", "profile", "my_invites", "new_invite"
    ]


class WorkHoursDay(CallbackData, prefix="wh"):
    action: Literal["pick", "day_off", "done", "back"]
    day: str = ""  # "mon".."sun" for pick/day_off/back, empty for "done"


class WorkHoursHour(CallbackData, prefix="whh"):
    day: str  # "mon".."sun"
    phase: Literal["start", "end"]
    hour: int  # 7..22
    start_hour: int = 0  # valid only when phase == "end"


class LanguageCallback(CallbackData, prefix="lang"):
    lang: Literal["ru", "hy"]
