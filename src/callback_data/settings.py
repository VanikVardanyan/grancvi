from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class SettingsCallback(CallbackData, prefix="set"):
    section: Literal["services", "hours", "breaks"]
