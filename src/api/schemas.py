from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MasterOut(BaseModel):
    id: UUID
    name: str
    specialty: str
    is_public: bool
    timezone: str


class ServiceOut(BaseModel):
    id: UUID
    name: str
    duration_min: int
    price_amd: int | None = None


class DayCapacityOut(BaseModel):
    date: date
    has_capacity: bool


class MonthSlotsOut(BaseModel):
    days: list[DayCapacityOut]


class SlotOut(BaseModel):
    start_at_utc: datetime


class BookingCreateIn(BaseModel):
    master_id: UUID
    service_id: UUID
    start_at_utc: datetime
    client_name: str = Field(..., min_length=1, max_length=120)
    client_phone: str | None = Field(default=None, max_length=40)


class BookingCreateOut(BaseModel):
    appointment_id: UUID
    status: str


class BookingMineOut(BaseModel):
    id: UUID
    master_name: str
    service_name: str
    start_at_utc: datetime
    status: str


class OkOut(BaseModel):
    ok: bool = True
