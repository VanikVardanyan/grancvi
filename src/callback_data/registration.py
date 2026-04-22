from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class SpecialtyHintCallback(CallbackData, prefix="sph"):
    hint: Literal["hair", "dentist", "nails", "cosmetologist", "custom"]


class SlugConfirmCallback(CallbackData, prefix="slc"):
    action: Literal["use", "change"]
