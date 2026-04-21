from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class SlotCallback(CallbackData, prefix="slot"):
    hour: int
    minute: int
