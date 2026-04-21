from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class MasterView(StatesGroup):
    """States for the /client flow: search query, then editing notes."""

    SearchingClient = State()
    EditingNotes = State()
