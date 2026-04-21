from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class ApprovalCallback(CallbackData, prefix="appr"):
    action: Literal["confirm", "reject", "history"]
    appointment_id: UUID
