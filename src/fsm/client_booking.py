from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ClientBooking(StatesGroup):
    ChoosingService = State()
    ChoosingDate = State()
    ChoosingTime = State()
    EnteringName = State()
    EnteringPhone = State()
    Confirming = State()
