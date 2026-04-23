from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class AdminMasterCallback(CallbackData, prefix="adm"):
    master_id: UUID
    action: Literal["view", "back"]


class BlockCallback(CallbackData, prefix="blk"):
    master_id: UUID
    block: bool


class AdminNewSalonCallback(CallbackData, prefix="ans"):
    pass
