from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class ProfileFieldCallback(CallbackData, prefix="pf"):
    field: Literal["name", "specialty", "slug"]
