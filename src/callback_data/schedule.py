from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class DayPickCallback(CallbackData, prefix="dpk"):
    """A /week day button → render that day's schedule."""

    ymd: str  # ISO YYYY-MM-DD


class DayNavCallback(CallbackData, prefix="dnv"):
    """Day-schedule bottom-bar navigation: today / tomorrow / week / calendar."""

    action: Literal["today", "tomorrow", "week", "calendar", "add"]
