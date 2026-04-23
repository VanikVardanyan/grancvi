from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SalonRegister(StatesGroup):
    waiting_lang = State()
    waiting_name = State()
    waiting_slug_confirm = State()
    waiting_custom_slug = State()
