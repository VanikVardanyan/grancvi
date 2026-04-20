from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData


class LangPickCallback(CallbackData, prefix="lang"):
    lang: Literal["ru", "hy"]
