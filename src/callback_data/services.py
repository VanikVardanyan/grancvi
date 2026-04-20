from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class ServiceAction(CallbackData, prefix="svc"):
    action: Literal["add", "edit", "delete", "edit_name", "edit_duration", "toggle", "back"]
    service_id: UUID | None = None
