from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.api.errors import ApiError
from src.api.schemas import (
    PublicMasterOut,
    PublicMonthDayOut,
    PublicMonthSlotsOut,
    PublicServiceOut,
    PublicSlotOut,
    PublicSlugOut,
)
from src.db.models import Master, Salon, Specialty
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.utils.time import now_utc

router = APIRouter(prefix="/v1/public", tags=["public"])


async def _resolve_specialty_text(session: AsyncSession, raw: str | None, lang: str) -> str | None:
    """Convert a comma-separated mix of specialty codes and free-form
    text into a single human-readable string in `lang` (ru/hy).

    The masters.specialty_text field stores whatever the master picked
    in the profile UI: any combination of canonical codes
    (`hairdresser_women`) and free text (`Колорист`). Codes resolve via
    the specialties table; non-codes pass through unchanged so a
    master's custom specialty isn't dropped on the floor.
    """
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        return None
    codes = {p for p in parts if p.replace("_", "").isalnum() and p.islower()}
    name_map: dict[str, str] = {}
    if codes:
        rows = await session.scalars(select(Specialty).where(Specialty.code.in_(codes)))
        for s in rows.all():
            name_map[s.code] = s.name_hy if lang == "hy" else s.name_ru
    pretty = [name_map.get(p, p) for p in parts]
    return ", ".join(pretty)


@router.get("/by-slug/{slug}", response_model=PublicSlugOut)
async def by_slug(
    slug: str,
    lang: str = Query("ru", pattern="^(ru|hy)$"),
    session: AsyncSession = Depends(get_session),
) -> PublicSlugOut:
    """Resolve a short URL slug to a master or salon.

    Used by the grancvi.am/<slug> smart-redirect lander: it calls this
    endpoint, decides whether to deep-link into the TMA as
    `master_<slug>` or `salon_<slug>`, and uses the returned profile
    fields to render a fallback card when Telegram isn't available.

    `lang` controls how `specialty` is rendered — codes get translated
    via the specialties table; the lander passes the user's UI lang.
    """
    master = await session.scalar(select(Master).where(Master.slug == slug))
    if master is not None:
        return PublicSlugOut(
            kind="master",
            slug=master.slug,
            name=master.name,
            specialty=await _resolve_specialty_text(session, master.specialty_text, lang),
            phone=master.phone if master.phone_public else None,
            is_public=master.is_public,
        )
    salon = await session.scalar(select(Salon).where(Salon.slug == slug))
    if salon is not None:
        return PublicSlugOut(
            kind="salon",
            slug=salon.slug,
            name=salon.name,
            is_public=salon.is_public,
        )
    raise ApiError("not_found", "slug not found", status_code=404)


def _master_bookable(master: Master) -> bool:
    return master.is_public is True and master.blocked_at is None


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


@router.get("/masters/{slug}", response_model=PublicMasterOut)
async def public_master_by_slug(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> PublicMasterOut:
    master = await MasterRepository(session).by_slug(slug)
    if master is None or not _master_bookable(master):
        raise ApiError("not_found", "master not found", status_code=404)
    return PublicMasterOut(
        id=master.id,
        name=master.name,
        slug=master.slug,
        specialty=master.specialty_text or None,
        phone=master.phone if master.phone_public and master.phone else None,
        lang=master.lang,
    )


@router.get("/masters/{slug}/services", response_model=list[PublicServiceOut])
async def public_master_services(
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> list[PublicServiceOut]:
    master = await MasterRepository(session).by_slug(slug)
    if master is None or not _master_bookable(master):
        raise ApiError("not_found", "master not found", status_code=404)
    services = await ServiceRepository(session).list_active(master.id)
    return [
        PublicServiceOut(id=s.id, name=s.name, duration_min=s.duration_min, price_amd=s.price_amd)
        for s in services
    ]


@router.get("/masters/{slug}/slots/month", response_model=PublicMonthSlotsOut)
async def public_master_slots_month(
    slug: str,
    service_id: UUID = Query(...),
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    session: AsyncSession = Depends(get_session),
) -> PublicMonthSlotsOut:
    master = await MasterRepository(session).by_slug(slug)
    if master is None or not _master_bookable(master):
        raise ApiError("not_found", "master not found", status_code=404)
    service = await ServiceRepository(session).get(service_id, master_id=master.id)
    if service is None or not service.active:
        raise ApiError("not_found", "service not found", status_code=404)

    try:
        month_date = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise ApiError("bad_input", "month must be YYYY-MM", status_code=400) from exc

    svc = BookingService(session)
    loads = await svc.get_month_load(
        master=master, service=service, month=month_date, now=now_utc()
    )
    return PublicMonthSlotsOut(
        days=[
            PublicMonthDayOut(date=d.isoformat(), has_capacity=count > 0)
            for d, count in sorted(loads.items())
        ]
    )


@router.get("/masters/{slug}/slots/day", response_model=list[PublicSlotOut])
async def public_master_slots_day(
    slug: str,
    service_id: UUID = Query(...),
    date: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    session: AsyncSession = Depends(get_session),
) -> list[PublicSlotOut]:
    master = await MasterRepository(session).by_slug(slug)
    if master is None or not _master_bookable(master):
        raise ApiError("not_found", "master not found", status_code=404)
    service = await ServiceRepository(session).get(service_id, master_id=master.id)
    if service is None or not service.active:
        raise ApiError("not_found", "service not found", status_code=404)

    try:
        day = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ApiError("bad_input", "date must be YYYY-MM-DD", status_code=400) from exc

    svc = BookingService(session)
    slots = await svc.get_free_slots(master, service, day, now=now_utc())
    return [PublicSlotOut(start_at_utc=_ensure_utc(s)) for s in slots]
