from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_master
from src.api.deps import get_session
from src.api.errors import ApiError
from src.api.schemas import (
    BookingCreateOut,
    MasterAppointmentOut,
    MasterManualBookingIn,
    MasterProfileIn,
    MasterProfileOut,
    MasterScheduleIn,
    MasterScheduleOut,
    MasterServiceOut,
    OkOut,
    ServiceCreateIn,
    ServiceUpdateIn,
)
from src.db.models import Appointment, Client, Master, Service
from src.exceptions import InvalidSlug, InvalidState, NotFound, ReservedSlug, SlotAlreadyTaken
from src.repositories.appointments import AppointmentRepository
from src.repositories.clients import ClientRepository
from src.repositories.masters import MasterRepository
from src.services.booking import BookingService
from src.services.reminders import ReminderService
from src.services.slug import SlugService

router = APIRouter(prefix="/v1/master/me", tags=["master"])


_VISIBLE_STATUSES: frozenset[str] = frozenset({"pending", "confirmed", "completed", "no_show"})


@router.get("/appointments", response_model=list[MasterAppointmentOut])
async def list_my_appointments(
    from_date: str = Query(..., alias="from", description="YYYY-MM-DD, master local"),
    to_date: str = Query(..., alias="to", description="YYYY-MM-DD, master local, inclusive"),
    master: Master = Depends(require_master),
    session: AsyncSession = Depends(get_session),
) -> list[MasterAppointmentOut]:
    """Return the master's appointments in a local-date range [from, to].

    Status filter mirrors the schedule view in the bot — cancelled/rejected
    are omitted. Both dates are interpreted in the master's timezone and the
    range is half-open `[from_start_local, to_end_local+1day)`.
    """
    try:
        d_from = date.fromisoformat(from_date)
        d_to = date.fromisoformat(to_date)
    except ValueError as exc:
        raise ApiError("bad_input", "dates must be YYYY-MM-DD", status_code=400) from exc
    if d_to < d_from:
        raise ApiError("bad_input", "`to` must be ≥ `from`", status_code=400)
    if (d_to - d_from).days > 62:
        raise ApiError("bad_input", "range too wide (max 62 days)", status_code=400)

    tz = ZoneInfo(master.timezone)
    start_local = datetime(d_from.year, d_from.month, d_from.day, tzinfo=tz)
    end_local = datetime(d_to.year, d_to.month, d_to.day, tzinfo=tz) + timedelta(days=1)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)

    stmt = (
        select(
            Appointment.id,
            Appointment.start_at,
            Appointment.end_at,
            Appointment.status,
            Appointment.source,
            Client.name.label("client_name"),
            Client.phone.label("client_phone"),
            Service.name.label("service_name"),
            Service.duration_min.label("duration_min"),
        )
        .join(Client, Client.id == Appointment.client_id)
        .join(Service, Service.id == Appointment.service_id)
        .where(
            Appointment.master_id == master.id,
            Appointment.start_at >= start_utc,
            Appointment.start_at < end_utc,
            Appointment.status.in_(list(_VISIBLE_STATUSES)),
        )
        .order_by(Appointment.start_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        MasterAppointmentOut(
            id=row.id,
            client_name=row.client_name,
            client_phone=row.client_phone,
            service_name=row.service_name,
            duration_min=row.duration_min,
            start_at_utc=row.start_at.astimezone(UTC),
            end_at_utc=row.end_at.astimezone(UTC),
            status=row.status,
            source=row.source,
        )
        for row in rows
    ]


_WEEKDAYS: frozenset[str] = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})


def _validate_schedule_map(
    mapping: dict[str, list[list[str]]] | None,
    field: str,
) -> None:
    if mapping is None:
        return
    for key, intervals in mapping.items():
        if key not in _WEEKDAYS:
            raise ApiError("bad_input", f"{field}: unknown weekday '{key}'", status_code=400)
        for pair in intervals:
            if len(pair) != 2:
                raise ApiError(
                    "bad_input",
                    f"{field}[{key}]: interval must be [start, end]",
                    status_code=400,
                )
            start, end = pair
            for t_str in (start, end):
                try:
                    h, m = t_str.split(":")
                    hh, mm = int(h), int(m)
                    if not (0 <= hh < 24 and 0 <= mm < 60):
                        raise ValueError
                except (ValueError, AttributeError) as exc:
                    raise ApiError(
                        "bad_input",
                        f"{field}[{key}]: bad time '{t_str}' (expected HH:MM)",
                        status_code=400,
                    ) from exc
            if start >= end:
                raise ApiError(
                    "bad_input",
                    f"{field}[{key}]: start must be before end",
                    status_code=400,
                )


_SLUG_COOLDOWN = timedelta(days=30)


def _profile_out(m: Master) -> MasterProfileOut:
    next_change = (
        m.slug_changed_at + _SLUG_COOLDOWN
        if m.slug_changed_at is not None
        else None
    )
    return MasterProfileOut(
        id=m.id,
        name=m.name,
        specialty=m.specialty_text or "",
        slug=m.slug,
        phone=m.phone,
        timezone=m.timezone,
        lang=m.lang,
        is_public=m.is_public,
        slug_next_change_at=next_change,
    )


@router.get("/profile", response_model=MasterProfileOut)
async def get_my_profile(
    master: Master = Depends(require_master),
) -> MasterProfileOut:
    return _profile_out(master)


@router.patch("/profile", response_model=MasterProfileOut)
async def update_my_profile(
    payload: MasterProfileIn,
    master: Master = Depends(require_master),
    session: AsyncSession = Depends(get_session),
) -> MasterProfileOut:
    if payload.slug is not None and payload.slug != master.slug:
        # 30-day cooldown — stops thrashing and keeps printed QR stickers
        # meaningful even though we redirect past slugs.
        if master.slug_changed_at is not None:
            next_allowed = master.slug_changed_at + _SLUG_COOLDOWN
            if datetime.now(UTC) < next_allowed:
                raise ApiError(
                    "slug_rate_limited",
                    f"slug can be changed again at {next_allowed.isoformat()}",
                    status_code=429,
                )
        slug_svc = SlugService(session)
        try:
            SlugService.validate(payload.slug)
        except ReservedSlug as exc:
            raise ApiError("slug_reserved", "slug is reserved", status_code=400) from exc
        except InvalidSlug as exc:
            raise ApiError("slug_invalid", str(exc), status_code=400) from exc
        if await slug_svc.is_taken(payload.slug):
            raise ApiError("slug_taken", "slug already taken", status_code=409)
        # Goes through the repo so the old slug is stashed in past_slugs
        # and old QR / deep links still resolve to this master.
        await MasterRepository(session).update_slug(master.id, payload.slug)

    if payload.timezone is not None:
        try:
            ZoneInfo(payload.timezone)
        except Exception as exc:
            raise ApiError(
                "bad_input",
                f"unknown timezone '{payload.timezone}'",
                status_code=400,
            ) from exc
        master.timezone = payload.timezone

    if payload.name is not None:
        master.name = payload.name.strip()
    if payload.specialty is not None:
        master.specialty_text = payload.specialty.strip()
    if payload.phone is not None:
        master.phone = payload.phone.strip() or None
    if payload.lang is not None:
        master.lang = payload.lang
    if payload.is_public is not None:
        master.is_public = payload.is_public

    await session.commit()
    return _profile_out(master)


@router.get("/schedule", response_model=MasterScheduleOut)
async def get_my_schedule(
    master: Master = Depends(require_master),
) -> MasterScheduleOut:
    return MasterScheduleOut(
        work_hours=master.work_hours or {},
        breaks=master.breaks or {},
        slot_step_min=master.slot_step_min,
        timezone=master.timezone,
    )


@router.patch("/schedule", response_model=MasterScheduleOut)
async def update_my_schedule(
    payload: MasterScheduleIn,
    master: Master = Depends(require_master),
    session: AsyncSession = Depends(get_session),
) -> MasterScheduleOut:
    _validate_schedule_map(payload.work_hours, "work_hours")
    _validate_schedule_map(payload.breaks, "breaks")

    if payload.work_hours is not None:
        master.work_hours = payload.work_hours
    if payload.breaks is not None:
        master.breaks = payload.breaks
    if payload.slot_step_min is not None:
        master.slot_step_min = payload.slot_step_min
    await session.commit()
    return MasterScheduleOut(
        work_hours=master.work_hours or {},
        breaks=master.breaks or {},
        slot_step_min=master.slot_step_min,
        timezone=master.timezone,
    )


@router.post("/appointments", response_model=BookingCreateOut, status_code=201)
async def create_manual_appointment(
    payload: MasterManualBookingIn,
    master: Master = Depends(require_master),
    session: AsyncSession = Depends(get_session),
) -> BookingCreateOut:
    """Master adds an appointment for a walk-in / call-in client.

    Creates (or reuses by phone) a Client row owned by this master and a
    confirmed Appointment in one transaction. 409 if the slot was taken
    concurrently.
    """
    service = await session.scalar(
        select(Service).where(Service.id == payload.service_id, Service.master_id == master.id)
    )
    if service is None or not service.active:
        raise ApiError("not_found", "service not found", status_code=404)

    start_at_utc = (
        payload.start_at_utc
        if payload.start_at_utc.tzinfo is not None
        else payload.start_at_utc.replace(tzinfo=UTC)
    )

    client_repo = ClientRepository(session)
    phone = (payload.client_phone or "").strip() or None
    name = payload.client_name.strip()
    if phone:
        client = await client_repo.upsert_by_phone(
            master_id=master.id, phone=phone, name=name, tg_id=None
        )
    else:
        client = await client_repo.create_anonymous(master_id=master.id, name=name)

    reminder_svc = ReminderService(session)
    svc = BookingService(session, reminder_service=reminder_svc)
    try:
        appt = await svc.create_manual(
            master=master,
            client=client,
            service=service,
            start_at=start_at_utc,
            comment=(payload.comment or "").strip() or None,
        )
    except SlotAlreadyTaken as exc:
        raise ApiError("slot_taken", "slot already taken", status_code=409) from exc

    return BookingCreateOut(appointment_id=appt.id, status=appt.status)


def _service_to_out(s: Service) -> MasterServiceOut:
    return MasterServiceOut(
        id=s.id,
        name=s.name,
        duration_min=s.duration_min,
        price_amd=s.price_amd,
        active=s.active,
    )


@router.get("/services", response_model=list[MasterServiceOut])
async def list_my_services(
    master: Master = Depends(require_master),
    session: AsyncSession = Depends(get_session),
) -> list[MasterServiceOut]:
    """Return all services owned by the caller (including inactive ones).

    Ordered by `position` then `created_at` — matches the master's bot view.
    """
    stmt = (
        select(Service)
        .where(Service.master_id == master.id)
        .order_by(Service.position.asc(), Service.created_at.asc())
    )
    rows = list((await session.scalars(stmt)).all())
    return [_service_to_out(s) for s in rows]


@router.post("/services", response_model=MasterServiceOut, status_code=201)
async def create_my_service(
    payload: ServiceCreateIn,
    master: Master = Depends(require_master),
    session: AsyncSession = Depends(get_session),
) -> MasterServiceOut:
    """Create a new service on the caller's master profile."""
    service = Service(
        master_id=master.id,
        name=payload.name.strip(),
        duration_min=payload.duration_min,
        price_amd=payload.price_amd,
    )
    session.add(service)
    await session.flush()
    await session.commit()
    return _service_to_out(service)


@router.patch("/services/{service_id}", response_model=MasterServiceOut)
async def update_my_service(
    service_id: UUID,
    payload: ServiceUpdateIn,
    master: Master = Depends(require_master),
    session: AsyncSession = Depends(get_session),
) -> MasterServiceOut:
    """Partially update a service owned by the caller."""
    service = await session.scalar(
        select(Service).where(Service.id == service_id, Service.master_id == master.id)
    )
    if service is None:
        raise ApiError("not_found", "service not found", status_code=404)

    if payload.name is not None:
        service.name = payload.name.strip()
    if payload.duration_min is not None:
        service.duration_min = payload.duration_min
    if payload.price_amd is not None:
        service.price_amd = payload.price_amd
    if payload.active is not None:
        service.active = payload.active

    await session.commit()
    return _service_to_out(service)


@router.post("/appointments/{appointment_id}/cancel", response_model=OkOut)
async def cancel_my_appointment(
    appointment_id: UUID,
    master: Master = Depends(require_master),
    session: AsyncSession = Depends(get_session),
) -> OkOut:
    """Master cancels one of their appointments from the TMA dashboard.

    Only pending/confirmed can be cancelled. Triggers the same
    side-effects as the bot flow: status → cancelled, cancelled_by =
    "master", reminders suppressed. Client notification via the bot is
    handled by the existing cancel-notify path (not yet wired for API
    cancels — can be added in a follow-up).
    """
    appt_repo = AppointmentRepository(session)
    appt = await appt_repo.get(appointment_id)
    if appt is None or appt.master_id != master.id:
        raise ApiError("not_found", "appointment not found", status_code=404)

    svc = BookingService(session)
    try:
        await svc.cancel(appt.id, cancelled_by="master")
    except (NotFound, InvalidState) as exc:
        raise ApiError("cannot_cancel", "appointment cannot be cancelled", status_code=409) from exc

    reminder_svc = ReminderService(session)
    await reminder_svc.suppress_for_appointment(appt.id)
    await session.commit()
    return OkOut(ok=True)


@router.delete("/services/{service_id}", response_model=OkOut)
async def delete_my_service(
    service_id: UUID,
    master: Master = Depends(require_master),
    session: AsyncSession = Depends(get_session),
) -> OkOut:
    """Soft-delete a service (sets active=False).

    Hard-delete would break existing appointments' FK. Services with
    historical appointments must stay in DB.
    """
    service = await session.scalar(
        select(Service).where(Service.id == service_id, Service.master_id == master.id)
    )
    if service is None:
        raise ApiError("not_found", "service not found", status_code=404)
    service.active = False
    await session.commit()
    return OkOut(ok=True)
