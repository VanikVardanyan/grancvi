from __future__ import annotations

from typing import Literal
from uuid import UUID

from aiogram.filters.callback_data import CallbackData


class SalonSlugConfirmCallback(CallbackData, prefix="ssc"):
    action: Literal["use", "change"]


class SalonMasterPickCallback(CallbackData, prefix="smp"):
    master_id: UUID


class SalonSlotPickCallback(CallbackData, prefix="sslt"):
    slot_iso: str


class SalonNewClientCallback(CallbackData, prefix="snc"):
    action: Literal["new", "search"]


class SalonSkipPhoneCallback(CallbackData, prefix="sspp"):
    pass


class SalonConfirmApptCallback(CallbackData, prefix="scap"):
    action: Literal["save", "cancel"]
