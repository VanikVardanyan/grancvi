from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class CalendarCallback(CallbackData, prefix="cal"):
    """Calendar cell / navigation button.

    action:
      - pick: user picked a concrete date (year, month, day).
      - nav: prev/next month (day=0, sign encoded in month: >0 go forward, <0 back).
      - noop: disabled cell (past day, empty grid slot). Handler ignores.
    """

    action: Literal["pick", "nav", "noop"]
    year: int
    month: int
    day: int = 0
