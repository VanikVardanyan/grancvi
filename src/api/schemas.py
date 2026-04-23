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


class MeProfileOut(BaseModel):
    """Compact identity card returned by GET /v1/me.

    Fields depend on role:
      - client       → only tg_id + first_name
      - master       → tg_id, first_name, master_id, master_name, slug, specialty
      - salon_owner  → tg_id, first_name, salon_id, salon_name, slug
    """

    tg_id: int
    first_name: str
    # master-only
    master_id: UUID | None = None
    master_name: str | None = None
    slug: str | None = None
    specialty: str | None = None
    # salon-only
    salon_id: UUID | None = None
    salon_name: str | None = None


class MeOut(BaseModel):
    role: str  # "client" | "master" | "salon_owner"
    profile: MeProfileOut
