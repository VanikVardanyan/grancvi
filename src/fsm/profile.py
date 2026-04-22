from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ProfileEdit(StatesGroup):
    menu = State()
    waiting_name = State()
    waiting_specialty = State()
    waiting_slug = State()
