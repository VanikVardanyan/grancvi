from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class MarkPastCallback(CallbackData, prefix="mpa"):
    """Mark a past `confirmed` appointment as `completed` or `no_show`."""

    action: Literal["present", "no_show"]
    appointment_id: UUID
