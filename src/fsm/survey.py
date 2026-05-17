from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SurveyFeedback(StatesGroup):
    waiting_comment = State()
