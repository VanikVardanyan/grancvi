from __future__ import annotations

from datetime import UTC
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot
from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.api.auth import require_tg_user
from src.api.deps import get_app_bot, get_bot, get_session
from src.api.errors import ApiError
from src.api.schemas import (
    BookingCreateIn,
    BookingCreateOut,
    BookingMineOut,
    OkOut,
    VisitedMasterOut,
)
from src.config import settings
from src.db.models import Appointment, Client, Master, Service
from src.exceptions import InvalidState, NotFound, SlotAlreadyTaken
from src.repositories.clients import ClientRepository
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.services.reminders import ReminderService
from src.strings import strings
from src.utils.client_notify import notify_user
from src.utils.time import now_utc


def _open_app_kb() -> object:
    """InlineKeyboard with one WebApp button → TMA master dashboard.

    Works via both @grancviWebBot (primary) and the legacy token
    (fallback) — WebApp buttons only require the URL, no callback
    handler lives on the bot side.
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

    url = "https://app.jampord.am"
    label = "🚀 Открыть приложение"
    _ = settings  # keep import alive for future per-env overrides
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]]
    )


router = APIRouter(prefix="/v1/bookings", tags=["bookings"])
log: structlog.stdlib.BoundLogger = structlog.get_logger()


def _master_is_available(master_obj: Master) -> bool:
    return master_obj.is_public is True and master_obj.blocked_at is None


@router.post("", response_model=BookingCreateOut, status_code=201)
async def create_booking(
    payload: BookingCreateIn,
    tg_user: dict[str, Any] = Depends(require_tg_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    app_bot: Bot | None = Depends(get_app_bot),
) -> BookingCreateOut:
    master = await MasterRepository(session).by_id(payload.master_id)
    if master is None or not _master_is_available(master):
        raise ApiError("not_found", "master not found", status_code=404)

    service = await ServiceRepository(session).get(payload.service_id, master_id=master.id)
    if service is None or not service.active:
        raise ApiError("not_found", "service not found", status_code=404)

    start_at_utc = (
        payload.start_at_utc
        if payload.start_at_utc.tzinfo is not None
        else payload.start_at_utc.replace(tzinfo=UTC)
    ).astimezone(UTC)

    tg_id = int(tg_user["id"])
    client_repo = ClientRepository(session)
    if payload.client_phone:
        client = await client_repo.upsert_by_phone(
            master_id=master.id,
            phone=payload.client_phone,
            name=payload.client_name,
            tg_id=tg_id,
        )
    else:
        client = await client_repo.create_anonymous(
            master_id=master.id, name=payload.client_name, tg_id=tg_id
        )

    booking_svc = BookingService(session)

    try:
        appt = await booking_svc.create_pending(
            master=master,
            client=client,
            service=service,
            start_at=start_at_utc,
        )
    except SlotAlreadyTaken as exc:
        raise ApiError("slot_taken", "slot is no longer available", status_code=409) from exc

    tz = ZoneInfo(master.timezone)
    local = appt.start_at.astimezone(tz)
    text = strings.APPT_NOTIFY_MASTER.format(
        name=client.name,
        phone=client.phone or "—",
        service=service.name,
        duration=service.duration_min,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        weekday=strings.WEEKDAY_SHORT[local.weekday()],
    )
    # Notification carries a WebApp button → TMA dashboard, where the
    # pending card exposes Approve / Reject. WebApp buttons work on
    # both bots, so fallback still delivers a useful message.
    await notify_user(
        app_bot=app_bot,
        fallback_bot=bot,
        chat_id=master.tg_id,
        text=text,
        reply_markup=_open_app_kb(),
    )

    return BookingCreateOut(appointment_id=appt.id, status=appt.status)


@router.get("/mine", response_model=list[BookingMineOut])
async def list_my_bookings(
    tg_user: dict[str, Any] = Depends(require_tg_user),
    session: AsyncSession = Depends(get_session),
) -> list[BookingMineOut]:
    tg_id = int(tg_user["id"])
    MasterAlias = aliased(Master)
    ServiceAlias = aliased(Service)
    stmt = (
        select(
            Appointment.id,
            Appointment.start_at,
            Appointment.status,
            MasterAlias.name.label("master_name"),
            ServiceAlias.name.label("service_name"),
        )
        .join(Client, Client.id == Appointment.client_id)
        .join(MasterAlias, MasterAlias.id == Appointment.master_id)
        .join(ServiceAlias, ServiceAlias.id == Appointment.service_id)
        .where(
            Client.tg_id == tg_id,
            Appointment.start_at >= now_utc(),
            Appointment.status.in_(["pending", "confirmed"]),
        )
        .order_by(Appointment.start_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        BookingMineOut(
            id=row.id,
            master_name=row.master_name,
            service_name=row.service_name,
            start_at_utc=row.start_at.astimezone(UTC),
            status=row.status,
        )
        for row in rows
    ]


@router.get("/visited-masters", response_model=list[VisitedMasterOut])
async def list_visited_masters(
    tg_user: dict[str, Any] = Depends(require_tg_user),
    session: AsyncSession = Depends(get_session),
) -> list[VisitedMasterOut]:
    """Masters this client has ever booked with.

    Groups by master across all of the client's appointments in any status,
    returns one row per master sorted by most recent booking first. Lets a
    returning client re-book without needing the original QR/link.

    Only masters currently public and not blocked are returned.
    """
    tg_id = int(tg_user["id"])
    last_booked = func.max(Appointment.start_at).label("last_booked_at")
    stmt = (
        select(
            Master.id,
            Master.name,
            Master.slug,
            Master.specialty_text.label("specialty"),
            last_booked,
        )
        .join(Appointment, Appointment.master_id == Master.id)
        .join(Client, Client.id == Appointment.client_id)
        .where(
            and_(
                Client.tg_id == tg_id,
                Master.blocked_at.is_(None),
                Master.is_public.is_(True),
            )
        )
        .group_by(Master.id, Master.name, Master.slug, Master.specialty_text)
        .order_by(last_booked.desc())
        .limit(30)
    )
    rows = (await session.execute(stmt)).all()
    return [
        VisitedMasterOut(
            id=row.id,
            name=row.name,
            slug=row.slug,
            specialty=row.specialty or "",
            last_booked_at=row.last_booked_at.astimezone(UTC),
        )
        for row in rows
    ]


@router.post("/{appointment_id}/cancel", response_model=OkOut)
async def cancel_booking(
    appointment_id: UUID,
    tg_user: dict[str, Any] = Depends(require_tg_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    app_bot: Bot | None = Depends(get_app_bot),
) -> OkOut:
    tg_id = int(tg_user["id"])
    svc = BookingService(session)
    try:
        appt, client, master, service = await svc.cancel_by_client(appointment_id, tg_id=tg_id)
    except NotFound as exc:
        # NotFound is raised both for missing rows AND ownership mismatch — the
        # service intentionally does not distinguish to avoid leaking existence.
        # Per API contract, treat as 403 (not_owner) when the caller is authenticated.
        raise ApiError("not_owner", "not your appointment", status_code=403) from exc
    except InvalidState as exc:
        raise ApiError("cannot_cancel", "appointment cannot be cancelled", status_code=409) from exc

    reminder_svc = ReminderService(session)
    await reminder_svc.suppress_for_appointment(appt.id)
    await session.commit()

    tz = ZoneInfo(master.timezone)
    local = appt.start_at.astimezone(tz)
    text = strings.MASTER_NOTIFY_CLIENT_CANCELED.format(
        name=client.name,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        service=service.name,
    )
    await notify_user(
        app_bot=app_bot,
        fallback_bot=bot,
        chat_id=master.tg_id,
        text=text,
        reply_markup=_open_app_kb(),
    )

    return OkOut(ok=True)
