from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class WorkHoursEdit(StatesGroup):
    waiting_start = State()
    waiting_end = State()
