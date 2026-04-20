from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MasterRegister(StatesGroup):
    waiting_lang = State()
    waiting_name = State()
    waiting_phone = State()
