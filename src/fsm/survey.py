from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SurveyAdmin(StatesGroup):
    waiting_text = State()


class SurveyFeedback(StatesGroup):
    waiting_comment = State()
