from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import Bot
from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_salon
from src.api.deps import get_app_bot, get_bot, get_session
from src.api.errors import ApiError
from src.api.schemas import (
    AdminInviteOut,
    BookingCreateOut,
    MasterManualBookingIn,
    OkOut,
    SalonAppointmentOut,
    SalonMasterOut,
    SalonProfileOut,
    SalonRedirectIn,
)
from src.config import settings
from src.db.models import Appointment, Client, Master, Salon, Service
from src.exceptions import SlotAlreadyTaken
from src.repositories.clients import ClientRepository
from src.repositories.invites import InviteRepository
from src.services.booking import BookingService
from src.services.reminders import ReminderService
from src.strings import strings
from src.utils.client_notify import notify_user
from src.utils.time import now_utc

router = APIRouter(prefix="/v1/salon/me", tags=["salon"])


_VISIBLE_STATUSES: frozenset[str] = frozenset({"pending", "confirmed", "completed", "no_show"})


def _invite_link(code: str) -> str:
    return f"https://t.me/{settings.app_bot_username}?start=invite_{code}"


@router.get("", response_model=SalonProfileOut)
async def salon_profile(
    salon: Salon = Depends(require_salon),
    session: AsyncSession = Depends(get_session),
) -> SalonProfileOut:
    count = (
        await session.scalar(select(func.count(Master.id)).where(Master.salon_id == salon.id)) or 0
    )
    return SalonProfileOut(
        id=salon.id,
        name=salon.name,
        slug=salon.slug,
        masters_count=count,
    )


@router.get("/masters", response_model=list[SalonMasterOut])
async def salon_masters(
    salon: Salon = Depends(require_salon),
    session: AsyncSession = Depends(get_session),
) -> list[SalonMasterOut]:
    """Masters linked to this salon with per-master counters.

    `appointments_today` is resolved in the salon-owner's local tz — the
    owner looks at the dashboard in their browser, and the Salon row
    itself doesn't carry a timezone, so we fall back to the first
    master's tz. Good enough for a quick-glance workload gauge.
    """
    masters = list(
        (
            await session.scalars(
                select(Master).where(Master.salon_id == salon.id).order_by(Master.name)
            )
        ).all()
    )
    if not masters:
        return []

    tz = ZoneInfo(masters[0].timezone)
    today_local = datetime.now(tz).date()
    day_start_local = datetime(today_local.year, today_local.month, today_local.day, tzinfo=tz)
    start_utc = day_start_local.astimezone(UTC)
    end_utc = start_utc + timedelta(days=1)
    cutoff_30d = now_utc() - timedelta(days=30)

    today_counts = {
        mid: cnt
        for mid, cnt in (
            await session.execute(
                select(Appointment.master_id, func.count(Appointment.id))
                .where(
                    Appointment.master_id.in_([m.id for m in masters]),
                    Appointment.start_at >= start_utc,
                    Appointment.start_at < end_utc,
                    Appointment.status.in_(list(_VISIBLE_STATUSES)),
                )
                .group_by(Appointment.master_id)
            )
        ).all()
    }
    last30_counts = {
        mid: cnt
        for mid, cnt in (
            await session.execute(
                select(Appointment.master_id, func.count(Appointment.id))
                .where(
                    Appointment.master_id.in_([m.id for m in masters]),
                    Appointment.created_at >= cutoff_30d,
                )
                .group_by(Appointment.master_id)
            )
        ).all()
    }

    return [
        SalonMasterOut(
            id=m.id,
            name=m.name,
            slug=m.slug,
            specialty=m.specialty_text or "",
            is_public=m.is_public,
            blocked=m.blocked_at is not None,
            appointments_today=int(today_counts.get(m.id, 0)),
            appointments_30d=int(last30_counts.get(m.id, 0)),
        )
        for m in masters
    ]


@router.get("/appointments", response_model=list[SalonAppointmentOut])
async def salon_appointments(
    from_date: str = Query(..., alias="from"),
    to_date: str = Query(..., alias="to"),
    master_id: UUID | None = Query(default=None),
    salon: Salon = Depends(require_salon),
    session: AsyncSession = Depends(get_session),
) -> list[SalonAppointmentOut]:
    """Unified calendar across all masters of the salon (or a single one)."""
    try:
        d_from = date.fromisoformat(from_date)
        d_to = date.fromisoformat(to_date)
    except ValueError as exc:
        raise ApiError("bad_input", "dates must be YYYY-MM-DD", status_code=400) from exc
    if d_to < d_from:
        raise ApiError("bad_input", "`to` must be ≥ `from`", status_code=400)
    if (d_to - d_from).days > 62:
        raise ApiError("bad_input", "range too wide (max 62 days)", status_code=400)

    # Use the first master's timezone to map local dates to UTC; this
    # matches how salon_masters bucket "today" for the dashboard count.
    first = await session.scalar(select(Master).where(Master.salon_id == salon.id).limit(1))
    if first is None:
        return []
    tz = ZoneInfo(first.timezone)

    start_local = datetime(d_from.year, d_from.month, d_from.day, tzinfo=tz)
    end_local = datetime(d_to.year, d_to.month, d_to.day, tzinfo=tz) + timedelta(days=1)
    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)

    filters = [
        Master.salon_id == salon.id,
        Appointment.start_at >= start_utc,
        Appointment.start_at < end_utc,
        Appointment.status.in_(list(_VISIBLE_STATUSES)),
    ]
    if master_id is not None:
        filters.append(Appointment.master_id == master_id)

    stmt = (
        select(
            Appointment.id,
            Appointment.master_id,
            Master.name.label("master_name"),
            Appointment.start_at,
            Appointment.end_at,
            Appointment.status,
            Client.name.label("client_name"),
            Client.phone.label("client_phone"),
            Service.name.label("service_name"),
            Service.duration_min.label("duration_min"),
        )
        .join(Master, Master.id == Appointment.master_id)
        .join(Client, Client.id == Appointment.client_id)
        .join(Service, Service.id == Appointment.service_id)
        .where(and_(*filters))
        .order_by(Appointment.start_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        SalonAppointmentOut(
            id=row.id,
            master_id=row.master_id,
            master_name=row.master_name,
            client_name=row.client_name,
            client_phone=row.client_phone,
            service_name=row.service_name,
            duration_min=row.duration_min,
            start_at_utc=row.start_at.astimezone(UTC),
            end_at_utc=row.end_at.astimezone(UTC),
            status=row.status,
        )
        for row in rows
    ]


@router.post("/invites", response_model=AdminInviteOut, status_code=201)
async def salon_create_invite(
    salon: Salon = Depends(require_salon),
    session: AsyncSession = Depends(get_session),
) -> AdminInviteOut:
    """Invite a new master into THIS salon.

    Shares the AdminInviteOut shape so the web client can reuse the same
    copy/share sheet. On redemption MasterRegistrationService links the
    new master to this salon via invite.salon_id.
    """
    repo = InviteRepository(session)
    invite = await repo.create(
        created_by_tg_id=salon.owner_tg_id,
        kind="master",
        salon_id=salon.id,
    )
    await session.commit()
    return AdminInviteOut(
        code=invite.code,
        kind=invite.kind,
        link=_invite_link(invite.code),
        expires_at=invite.expires_at,
    )


@router.post("/masters/{master_id}/remove", response_model=OkOut)
async def salon_remove_master(
    master_id: UUID,
    salon: Salon = Depends(require_salon),
    session: AsyncSession = Depends(get_session),
) -> OkOut:
    """Detach a master from this salon (soft; master account survives).

    Leaves future pending/confirmed appointments intact — the master
    still owns them and can handle the handover with clients directly.
    """
    master = await session.scalar(
        select(Master).where(Master.id == master_id, Master.salon_id == salon.id)
    )
    if master is None:
        raise ApiError("not_found", "master not in this salon", status_code=404)
    master.salon_id = None
    await session.commit()
    return OkOut(ok=True)


@router.post("/masters/{master_id}/redirect", response_model=OkOut)
async def salon_set_master_redirect(
    master_id: UUID,
    payload: SalonRedirectIn,
    salon: Salon = Depends(require_salon),
    session: AsyncSession = Depends(get_session),
) -> OkOut:
    """Redirect a master's public slug to another master or the salon landing.

    Both None → clear the redirect. Exactly one target must be set. The
    master must have belonged to this salon at least at some point —
    we accept both currently-linked (`salon_id = salon.id`) and detached
    masters whose existing `redirect_salon_id` already points here, so a
    salon owner can still edit the redirect after detaching.
    """
    if payload.to_master_id is not None and payload.to_salon_id is not None:
        raise ApiError("bad_input", "set only one redirect target", status_code=400)

    master = await session.scalar(
        select(Master).where(
            Master.id == master_id,
            (Master.salon_id == salon.id) | (Master.redirect_salon_id == salon.id),
        )
    )
    if master is None:
        raise ApiError("not_found", "master not in this salon", status_code=404)

    if payload.to_master_id is None and payload.to_salon_id is None:
        master.redirect_master_id = None
        master.redirect_salon_id = None
        await session.commit()
        return OkOut(ok=True)

    if payload.to_master_id is not None:
        # Target must be a master in this salon to avoid arbitrary cross-
        # salon redirects.
        target = await session.scalar(
            select(Master).where(
                Master.id == payload.to_master_id,
                Master.salon_id == salon.id,
            )
        )
        if target is None:
            raise ApiError("not_found", "target master not in this salon", status_code=404)
        if target.id == master.id:
            raise ApiError("bad_input", "cannot redirect to self", status_code=400)
        master.redirect_master_id = target.id
        master.redirect_salon_id = None
    else:
        if payload.to_salon_id != salon.id:
            raise ApiError("bad_input", "can only redirect to own salon", status_code=400)
        master.redirect_master_id = None
        master.redirect_salon_id = salon.id

    await session.commit()
    return OkOut(ok=True)


@router.post("/masters/{master_id}/appointments", response_model=BookingCreateOut, status_code=201)
async def salon_create_manual_appointment(
    master_id: UUID,
    payload: MasterManualBookingIn,
    salon: Salon = Depends(require_salon),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    app_bot: Bot | None = Depends(get_app_bot),
) -> BookingCreateOut:
    """Salon receptionist books a walk-in / call-in onto one of the salon's
    masters. Same semantics as POST /v1/master/me/appointments — the
    appointment goes in as `confirmed`, the master sees it in their
    dashboard, and the salon-level calendar picks it up via the
    shared master_id.
    """
    master = await session.scalar(
        select(Master).where(Master.id == master_id, Master.salon_id == salon.id)
    )
    if master is None:
        raise ApiError("not_found", "master not in this salon", status_code=404)

    service = await session.scalar(
        select(Service).where(Service.id == payload.service_id, Service.master_id == master.id)
    )
    if service is None or not service.active:
        raise ApiError("not_found", "service not found", status_code=404)

    from datetime import UTC as _UTC

    start_at_utc = (
        payload.start_at_utc
        if payload.start_at_utc.tzinfo is not None
        else payload.start_at_utc.replace(tzinfo=_UTC)
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

    # Salon receptionist booked: tell the master so they see the new
    # appointment even before opening the dashboard.
    from zoneinfo import ZoneInfo as _Zone

    tz = _Zone(master.timezone)
    local = appt.start_at.astimezone(tz)
    try:
        text = strings.APPT_NOTIFY_MASTER.format(
            name=client.name,
            phone=client.phone or "—",
            service=service.name,
            duration=service.duration_min,
            date=local.strftime("%d.%m.%Y"),
            time=local.strftime("%H:%M"),
            weekday=strings.WEEKDAY_SHORT[local.weekday()],
        )
        await notify_user(app_bot=app_bot, fallback_bot=bot, chat_id=master.tg_id, text=text)
    except Exception:
        pass

    return BookingCreateOut(appointment_id=appt.id, status=appt.status)
