from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MasterAdd(StatesGroup):
    PickingClient = State()
    SearchingClient = State()
    NewClientName = State()
    NewClientPhone = State()
    PickingService = State()
    PickingDate = State()
    PickingSlot = State()
    EnteringCustomTime = State()
    EnteringComment = State()
    Confirming = State()
