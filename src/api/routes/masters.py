from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.errors import ApiError
from src.api.schemas import (
    DayCapacityOut,
    MasterOut,
    MasterRedirectOut,
    MonthSlotsOut,
    ServiceOut,
    SlotOut,
)
from src.db.models import Salon
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.utils.time import now_utc

router = APIRouter(prefix="/v1/masters", tags=["masters"])


def _master_is_available(master_obj: object) -> bool:
    return (
        getattr(master_obj, "is_public", False) is True
        and getattr(master_obj, "blocked_at", None) is None
    )


@router.get("/by-slug/{slug}", response_model=MasterOut)
async def get_master_by_slug(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> MasterOut:
    master = await MasterRepository(session).by_slug(slug)
    if master is None:
        raise ApiError("not_found", "master not found", status_code=404)

    redirect: MasterRedirectOut | None = None
    if master.redirect_master_id is not None:
        target = await MasterRepository(session).by_id(master.redirect_master_id)
        if target is not None and _master_is_available(target):
            redirect = MasterRedirectOut(kind="master", slug=target.slug, name=target.name)
    elif master.redirect_salon_id is not None:
        salon = await session.scalar(select(Salon).where(Salon.id == master.redirect_salon_id))
        if salon is not None:
            redirect = MasterRedirectOut(kind="salon", slug=salon.slug, name=salon.name)

    # If the master themselves is no longer available but a redirect is
    # set, still return their row so the client can show the banner. If
    # neither available nor redirecting — 404.
    if not _master_is_available(master) and redirect is None:
        raise ApiError("not_found", "master not found", status_code=404)

    return MasterOut(
        id=master.id,
        name=master.name,
        specialty=master.specialty_text,
        is_public=master.is_public,
        timezone=master.timezone,
        redirect_to=redirect,
    )


@router.get("/{master_id}/services", response_model=list[ServiceOut])
async def list_master_services(
    master_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> list[ServiceOut]:
    master = await MasterRepository(session).by_id(master_id)
    if master is None or not _master_is_available(master):
        raise ApiError("not_found", "master not found", status_code=404)
    services = await ServiceRepository(session).list_active(master_id)
    return [
        ServiceOut(
            id=s.id,
            name=s.name,
            duration_min=s.duration_min,
            price_amd=s.price_amd,
            preset_code=s.preset_code,
        )
        for s in services
    ]


@router.get("/{master_id}/slots")
async def get_slots(
    master_id: UUID,
    service_id: UUID = Query(...),
    month: str | None = Query(default=None, description="YYYY-MM"),
    booking_date: str | None = Query(default=None, alias="date", description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_session),
) -> MonthSlotsOut | list[SlotOut]:
    if (month is None) == (booking_date is None):
        raise ApiError("bad_input", "pass exactly one of `month` or `date`", status_code=400)

    master = await MasterRepository(session).by_id(master_id)
    if master is None or not _master_is_available(master):
        raise ApiError("not_found", "master not found", status_code=404)
    service = await ServiceRepository(session).get(service_id, master_id=master_id)
    if service is None or not service.active:
        raise ApiError("not_found", "service not found", status_code=404)

    svc = BookingService(session)
    now = now_utc()

    if month is not None:
        try:
            month_date = datetime.strptime(month, "%Y-%m").date().replace(day=1)
        except ValueError as exc:
            raise ApiError("bad_input", "month must be YYYY-MM", status_code=400) from exc
        loads = await svc.get_month_load(master=master, service=service, month=month_date, now=now)
        days = [
            DayCapacityOut(date=d, has_capacity=count > 0) for d, count in sorted(loads.items())
        ]
        return MonthSlotsOut(days=days)

    assert booking_date is not None
    try:
        day = datetime.strptime(booking_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ApiError("bad_input", "date must be YYYY-MM-DD", status_code=400) from exc
    slots = await svc.get_free_slots(master, service, day, now=now)
    return [SlotOut(start_at_utc=_ensure_utc(s)) for s in slots]


def _ensure_utc(dt: datetime) -> datetime:
    """Return `dt` as tz-aware UTC datetime (free-slot math uses master tz)."""
    from datetime import UTC

    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
