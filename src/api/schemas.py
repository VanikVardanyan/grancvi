from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class MasterRedirectOut(BaseModel):
    """When a master has left a salon, GET /v1/masters/by-slug returns this
    attached to MasterOut so the client can render a "переехал" banner.
    """

    kind: str  # "master" | "salon"
    slug: str
    name: str


class MasterOut(BaseModel):
    id: UUID
    name: str
    specialty: str
    is_public: bool
    timezone: str
    redirect_to: MasterRedirectOut | None = None


class SalonPublicMasterOut(BaseModel):
    id: UUID
    name: str
    slug: str
    specialty: str


class SalonPublicOut(BaseModel):
    id: UUID
    name: str
    slug: str
    masters: list[SalonPublicMasterOut]


class SalonRedirectIn(BaseModel):
    """Only one of `to_master_id` / `to_salon_id` may be set. Both None
    clears the redirect.
    """

    to_master_id: UUID | None = None
    to_salon_id: UUID | None = None


class SearchHitOut(BaseModel):
    kind: str  # "master" | "salon"
    id: UUID
    name: str
    slug: str
    specialty: str | None = None  # masters only


class SearchResultOut(BaseModel):
    hits: list[SearchHitOut]


class InviteInfoOut(BaseModel):
    """Pre-flight read of an invite code — used by the TMA registration
    page to decide which form to render (master vs salon) and whether
    it's still valid before the user fills anything in.
    """

    code: str
    kind: str  # "master" | "salon_owner"
    valid: bool
    reason: str | None = None  # "expired" | "used" | "not_found" when invalid
    salon_id: UUID | None = None
    salon_name: str | None = None


class RegisterMasterIn(BaseModel):
    invite_code: str
    name: str = Field(..., min_length=1, max_length=200)
    specialty: str = Field(default="", max_length=200)
    slug: str | None = Field(default=None, min_length=3, max_length=32)
    lang: str = Field(default="ru", pattern="^(ru|hy)$")


class RegisterSalonIn(BaseModel):
    invite_code: str
    name: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=3, max_length=32)


class JoinSalonIn(BaseModel):
    invite_code: str


class VisitedMasterOut(BaseModel):
    """Compact master card for the client's 'previously booked' list.

    `last_booked_at` is the most recent appointment start time (UTC), used
    for most-recent-first sorting.
    """

    id: UUID
    name: str
    slug: str
    specialty: str
    last_booked_at: datetime


class ServiceOut(BaseModel):
    id: UUID
    name: str
    duration_min: int
    price_amd: int | None = None
    preset_code: str | None = None


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
    is_admin: bool = False


class AdminStatsOut(BaseModel):
    masters_active: int
    masters_blocked: int
    clients: int
    appointments_7d: int
    appointments_30d: int


class AdminMasterOut(BaseModel):
    id: UUID
    name: str
    slug: str
    specialty: str
    tg_id: int | None = None
    is_public: bool
    blocked: bool
    created_at: datetime
    appointments_total: int
    appointments_30d: int


class AdminInviteCreateIn(BaseModel):
    kind: str = Field(..., pattern="^(master|salon_owner)$")


class AdminInviteOut(BaseModel):
    code: str
    kind: str
    link: str
    expires_at: datetime


class SalonMasterOut(BaseModel):
    id: UUID
    name: str
    slug: str
    specialty: str
    is_public: bool
    blocked: bool
    appointments_today: int
    appointments_30d: int


class SalonProfileOut(BaseModel):
    id: UUID
    name: str
    slug: str
    masters_count: int


class SalonAppointmentOut(BaseModel):
    id: UUID
    master_id: UUID
    master_name: str
    client_name: str
    client_phone: str | None = None
    service_name: str
    duration_min: int
    start_at_utc: datetime
    end_at_utc: datetime
    status: str


class MasterAppointmentOut(BaseModel):
    """One row in the master's dashboard calendar view."""

    id: UUID
    client_name: str
    client_phone: str | None = None
    service_name: str
    duration_min: int
    start_at_utc: datetime
    end_at_utc: datetime
    status: str
    source: str


class MasterManualBookingIn(BaseModel):
    service_id: UUID
    start_at_utc: datetime
    client_name: str = Field(..., min_length=1, max_length=120)
    client_phone: str | None = Field(default=None, max_length=40)
    comment: str | None = Field(default=None, max_length=500)


class MasterScheduleOut(BaseModel):
    """Weekday schedule: work_hours[weekday] = [["HH:MM","HH:MM"], …]

    Weekday keys: mon, tue, wed, thu, fri, sat, sun.
    """

    work_hours: dict[str, list[list[str]]]
    breaks: dict[str, list[list[str]]]
    slot_step_min: int
    timezone: str


class MasterScheduleIn(BaseModel):
    work_hours: dict[str, list[list[str]]] | None = None
    breaks: dict[str, list[list[str]]] | None = None
    slot_step_min: int | None = Field(default=None, ge=5, le=120)


class MasterProfileOut(BaseModel):
    id: UUID
    name: str
    specialty: str
    slug: str
    phone: str | None = None
    timezone: str
    lang: str
    is_public: bool
    slug_next_change_at: datetime | None = None
    salon_id: UUID | None = None
    salon_name: str | None = None


class MasterProfileIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    specialty: str | None = Field(default=None, max_length=200)
    slug: str | None = Field(default=None, min_length=3, max_length=32)
    phone: str | None = Field(default=None, max_length=40)
    timezone: str | None = Field(default=None, max_length=64)
    lang: str | None = Field(default=None, pattern="^(ru|hy)$")
    is_public: bool | None = None


class MasterServiceOut(BaseModel):
    """Service row as seen by the owning master (includes inactive ones)."""

    id: UUID
    name: str
    duration_min: int
    price_amd: int | None = None
    active: bool
    preset_code: str | None = None


class ServiceCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    duration_min: int = Field(..., ge=1, le=24 * 60)
    price_amd: int | None = Field(default=None, ge=0)
    preset_code: str | None = Field(default=None, max_length=64)


class ServiceUpdateIn(BaseModel):
    """Partial update — only send what you want to change."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    duration_min: int | None = Field(default=None, ge=1, le=24 * 60)
    price_amd: int | None = Field(default=None, ge=0)
    active: bool | None = None
    preset_code: str | None = Field(default=None, max_length=64)
