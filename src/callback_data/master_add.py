from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class RecentClientCallback(CallbackData, prefix="mac"):
    """Client picker: UUID string, or the sentinel 'new'/'search'."""

    client_id: str


class PhoneDupCallback(CallbackData, prefix="mdp"):
    action: Literal["use", "retry"]
    client_id: UUID


class SkipCommentCallback(CallbackData, prefix="msc"):
    pass


class CustomTimeCallback(CallbackData, prefix="mct"):
    pass
