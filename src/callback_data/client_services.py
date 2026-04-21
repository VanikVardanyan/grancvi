from __future__ import annotations

from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class ClientServicePick(CallbackData, prefix="csvc"):
    service_id: UUID
