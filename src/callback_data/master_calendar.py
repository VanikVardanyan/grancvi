from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class MasterCalendarCallback(CallbackData, prefix="mca"):
    """Master-side calendar cell / nav. Distinct prefix from client's CalendarCallback."""

    action: Literal["pick", "nav", "noop"]
    year: int
    month: int
    day: int = 0
