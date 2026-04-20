from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ServiceAdd(StatesGroup):
    waiting_name = State()
    waiting_duration = State()


class ServiceEditName(StatesGroup):
    waiting_name = State()


class ServiceEditDuration(StatesGroup):
    waiting_duration = State()
