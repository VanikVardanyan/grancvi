from __future__ import annotations

import secrets
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import Bot
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_app_bot, get_bot, get_session
from src.api.errors import ApiError
from src.api.schemas import (
    PublicBookingIn,
    PublicBookingOut,
    PublicBookingStatusOut,
    PublicMasterOut,
    PublicMonthDayOut,
    PublicMonthSlotsOut,
    PublicServiceOut,
    PublicSlotOut,
    PublicSlugOut,
)
from src.config import settings
from src.db.models import Appointment, Master, Salon, Specialty
from src.exceptions import SlotAlreadyTaken
from src.repositories.clients import ClientRepository
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.strings import set_current_lang, strings
from src.utils.client_notify import notify_user
from src.utils.ratelimit import consume_token
from src.utils.recaptcha import verify_recaptcha
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
    lang: str = "hy",
    session: AsyncSession = Depends(get_session),
) -> PublicMasterOut:
    master = await MasterRepository(session).by_slug(slug)
    if master is None or not _master_bookable(master):
        raise ApiError("not_found", "master not found", status_code=404)
    return PublicMasterOut(
        id=master.id,
        name=master.name,
        slug=master.slug,
        specialty=await _resolve_specialty_text(session, master.specialty_text, lang),
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


# Rate-limit windows
_RL_IP_LIMIT = 5
_RL_IP_WINDOW = 60 * 60  # 1 hour
_RL_PHONE_LIMIT = 3
_RL_PHONE_WINDOW = 60 * 60


def _approve_kb(appointment_id: UUID) -> object:
    """Approve / Reject inline buttons. Same shape as bookings._approve_kb,
    inlined to avoid cross-route import. Caller MUST set the lang
    contextvar before invoking — strings.APPT_BTN_* read it on render.
    """
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.callback_data.approval import ApprovalCallback

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.APPT_BTN_CONFIRM,
                    callback_data=ApprovalCallback(
                        action="confirm", appointment_id=appointment_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=strings.APPT_BTN_REJECT,
                    callback_data=ApprovalCallback(
                        action="reject", appointment_id=appointment_id
                    ).pack(),
                ),
            ],
        ]
    )


@router.post("/bookings", response_model=PublicBookingOut, status_code=201)
async def public_create_booking(
    payload: PublicBookingIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    app_bot: Bot | None = Depends(get_app_bot),
) -> PublicBookingOut:
    """Public web-booking. No auth — only reCAPTCHA + rate-limit defend.

    Flow:
      1. reCAPTCHA verify (no-op if not configured)
      2. Rate-limit by IP and by (master, phone)
      3. Resolve master + service
      4. Upsert Client by (master_id, phone). Issue link_token if no
         tg_id and no existing token.
      5. Create Appointment via BookingService.create_pending(source="web")
      6. Notify master via notify_user + _approve_kb (master.lang context)
    """
    # 1. reCAPTCHA
    if not await verify_recaptcha(payload.recaptcha_token, expected_action="public_booking"):
        raise ApiError("captcha_failed", "captcha verification failed", status_code=400)

    # 2. Rate-limit by IP
    ip = request.client.host if request.client else "unknown"
    redis = request.app.state.redis
    if not await consume_token(
        redis, f"rl:pubbk:ip:{ip}", limit=_RL_IP_LIMIT, window_sec=_RL_IP_WINDOW
    ):
        raise ApiError("rate_limited", "too many requests, try later", status_code=429)

    # 3. Resolve master + service
    master = await MasterRepository(session).by_slug(payload.master_slug)
    if master is None or not _master_bookable(master):
        raise ApiError("not_found", "master not found", status_code=404)
    service = await ServiceRepository(session).get(payload.service_id, master_id=master.id)
    if service is None or not service.active:
        raise ApiError("not_found", "service not found", status_code=404)

    # Phone-scoped rate-limit (after master lookup so we can scope by master_id)
    if not await consume_token(
        redis,
        f"rl:pubbk:mp:{master.id}:{payload.client_phone}",
        limit=_RL_PHONE_LIMIT,
        window_sec=_RL_PHONE_WINDOW,
    ):
        raise ApiError("rate_limited", "too many bookings, try later", status_code=429)

    # 4. Upsert Client by (master_id, phone)
    client_repo = ClientRepository(session)
    client = await client_repo.upsert_by_phone(
        master_id=master.id,
        phone=payload.client_phone,
        name=payload.client_name.strip(),
        tg_id=None,  # web flow — no tg_id yet; never overwrites existing
    )
    # Issue link_token only if no tg_id linked AND no existing token.
    if client.tg_id is None and client.link_token is None:
        client.link_token = secrets.token_urlsafe(16)
        await session.flush()

    # 5. Create appointment
    booking_svc = BookingService(session)
    try:
        appt = await booking_svc.create_pending(
            master=master,
            client=client,
            service=service,
            start_at=payload.start_at_utc,
            source="web",
        )
    except SlotAlreadyTaken as exc:
        raise ApiError("slot_taken", "slot is no longer available", status_code=409) from exc

    # 6. Notify master in their lang
    set_current_lang(master.lang)
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
    sent = await notify_user(
        app_bot=app_bot,
        fallback_bot=bot,
        chat_id=master.tg_id,
        text=text,
        reply_markup=_approve_kb(appt.id),
    )
    if sent is not None:
        appt.master_notify_chat_id = sent.chat_id
        appt.master_notify_msg_id = sent.message_id
        appt.master_notify_via = sent.via
        await session.commit()

    # Build telegram_link_url. Prefer link_<token> for fresh web clients;
    # fallback to master_<slug> if there's no token (existing client).
    if client.link_token:
        tg_url = f"https://t.me/{settings.app_bot_username}?start=link_{client.link_token}"
    else:
        tg_url = f"https://t.me/{settings.app_bot_username}?start=master_{master.slug}"

    return PublicBookingOut(
        id=appt.id,
        master_name=master.name,
        service_name=service.name,
        start_at=appt.start_at,
        status=appt.status,
        telegram_link_url=tg_url,
    )


@router.get("/bookings/{booking_id}", response_model=PublicBookingStatusOut)
async def public_booking_status(
    booking_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> PublicBookingStatusOut:
    """Status check by UUID (UUID acts as bearer token — non-guessable).

    Used by the lander's localStorage to refresh appointment status on
    return visits. Returns minimal info: no phone, no client_id.
    """
    from src.db.models import Service as ServiceModel

    appt = await session.scalar(select(Appointment).where(Appointment.id == booking_id))
    if appt is None:
        raise ApiError("not_found", "booking not found", status_code=404)
    master = await session.scalar(select(Master).where(Master.id == appt.master_id))
    service = await session.scalar(select(ServiceModel).where(ServiceModel.id == appt.service_id))
    if master is None or service is None:
        raise ApiError("not_found", "booking not found", status_code=404)
    return PublicBookingStatusOut(
        id=appt.id,
        status=appt.status,
        master_name=master.name,
        service_name=service.name,
        start_at=appt.start_at,
    )
