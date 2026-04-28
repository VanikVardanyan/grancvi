from __future__ import annotations

from typing import Any

import structlog
from aiogram import Bot
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_tg_user
from src.api.deps import get_app_bot, get_bot, get_session
from src.api.errors import ApiError
from src.api.schemas import (
    InviteInfoOut,
    JoinSalonIn,
    MeOut,
    MeProfileOut,
    RegisterMasterIn,
    RegisterMasterSelfIn,
    RegisterSalonIn,
    RegisterSalonSelfIn,
)
from src.config import settings
from src.db.models import Master, Salon
from src.exceptions import (
    InvalidSlug,
    InviteAlreadyUsed,
    InviteExpired,
    InviteNotFound,
    ReservedSlug,
    SlugTaken,
)
from src.repositories.invites import InviteRepository
from src.repositories.salons import SalonRepository
from src.services.master_registration import MasterRegistrationService
from src.services.slug import SlugService
from src.utils.analytics import track_event
from src.utils.client_notify import notify_user

log: structlog.stdlib.BoundLogger = structlog.get_logger()


async def _notify_admins_of_new_signup(
    *,
    app_bot: Bot | None,
    bot: Bot,
    kind: str,
    name: str,
    slug: str,
    tg_id: int,
    first_name: str,
) -> None:
    """DM each admin with a heads-up about a fresh self-service registration.

    Self-service skips moderation (master/salon is public on creation),
    so this notification is informational + abuse-handle: if the slug
    looks bad / impersonates someone, admin can /block it.

    Best-effort: failures (admin never started the bot, transient
    Telegram errors) are swallowed by notify_user so one bad admin
    doesn't break delivery to the others.
    """
    if not settings.admin_tg_ids:
        return
    label = "мастер" if kind == "master" else "салон"
    text = (
        f"🆕 Новый {label}\n"
        f"👤 {name} (@{first_name}, tg_id={tg_id})\n"
        f"🔗 grancvi.am/{slug}\n\n"
        f"Если что-то не то — /block {slug}"
    )
    for admin_id in settings.admin_tg_ids:
        try:
            await notify_user(
                app_bot=app_bot,
                fallback_bot=bot,
                chat_id=admin_id,
                text=text,
            )
        except Exception as exc:
            log.warning("admin_notify_failed", admin_id=admin_id, err=repr(exc))


router = APIRouter(prefix="/v1/register", tags=["register"])


@router.get("/invite/{code}", response_model=InviteInfoOut)
async def invite_info(
    code: str,
    session: AsyncSession = Depends(get_session),
) -> InviteInfoOut:
    """Preview an invite before rendering the registration form.

    Tells the TMA whether to show the master or salon form, and
    surfaces "expired/used/not_found" errors immediately instead of
    waiting for the user to fill in the form.
    """
    invite = await InviteRepository(session).by_code(code)
    if invite is None:
        return InviteInfoOut(code=code, kind="", valid=False, reason="not_found")
    from datetime import UTC, datetime

    if invite.used_at is not None:
        return InviteInfoOut(code=code, kind=invite.kind, valid=False, reason="used")
    if invite.expires_at <= datetime.now(UTC):
        return InviteInfoOut(code=code, kind=invite.kind, valid=False, reason="expired")

    salon_name: str | None = None
    if invite.salon_id is not None:
        salon = await session.scalar(select(Salon).where(Salon.id == invite.salon_id))
        if salon is not None:
            salon_name = salon.name

    return InviteInfoOut(
        code=code,
        kind=invite.kind,
        valid=True,
        salon_id=invite.salon_id,
        salon_name=salon_name,
    )


async def _resolve_slug(session: AsyncSession, name: str, suggested: str | None) -> str:
    slug_svc = SlugService(session)
    if suggested:
        try:
            SlugService.validate(suggested)
        except ReservedSlug as exc:
            raise ApiError("slug_reserved", str(exc), status_code=409) from exc
        except InvalidSlug as exc:
            raise ApiError("slug_invalid", str(exc), status_code=400) from exc
        if await slug_svc.is_taken(suggested):
            raise ApiError("slug_taken", "slug already taken", status_code=409)
        return suggested
    return await slug_svc.generate_default(name)


@router.post("/master/self", response_model=MeOut, status_code=201)
async def register_master_self(
    payload: RegisterMasterSelfIn,
    tg_user: dict[str, Any] = Depends(require_tg_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    app_bot: Bot | None = Depends(get_app_bot),
) -> MeOut:
    """Self-service master registration — no invite required.

    Lands the new master with `is_public = false`; an admin must approve
    in /admin before the profile shows up in catalog/search results.
    """
    tg_id = int(tg_user["id"])
    first_name = str(tg_user.get("first_name") or payload.name)

    if await session.scalar(select(Master).where(Master.tg_id == tg_id)):
        raise ApiError("already_registered", "already a master", status_code=409)
    if await session.scalar(select(Salon).where(Salon.owner_tg_id == tg_id)):
        raise ApiError("already_registered", "already a salon owner", status_code=409)

    slug = await _resolve_slug(session, payload.name, payload.slug)

    try:
        master = await MasterRegistrationService(session).register_self(
            tg_id=tg_id,
            name=payload.name.strip(),
            specialty=payload.specialty.strip(),
            slug=slug,
            lang=payload.lang,
        )
    except SlugTaken as exc:
        raise ApiError("slug_taken", "slug already taken", status_code=409) from exc

    await session.commit()
    track_event(
        tg_id,
        "master_registered",
        {"method": "self_service", "slug": master.slug, "specialty": master.specialty_text or ""},
    )
    await _notify_admins_of_new_signup(
        app_bot=app_bot,
        bot=bot,
        kind="master",
        name=master.name,
        slug=master.slug,
        tg_id=tg_id,
        first_name=first_name,
    )
    is_admin = tg_id in settings.admin_tg_ids
    return MeOut(
        role="master",
        profile=MeProfileOut(
            tg_id=tg_id,
            first_name=first_name,
            master_id=master.id,
            master_name=master.name,
            slug=master.slug,
            specialty=master.specialty_text or None,
        ),
        is_admin=is_admin,
        onboarded=master.onboarded_at is not None,
    )


@router.post("/master", response_model=MeOut, status_code=201)
async def register_master(
    payload: RegisterMasterIn,
    tg_user: dict[str, Any] = Depends(require_tg_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    """Create a Master row for the caller and redeem the invite atomically.

    On success returns the same shape as /v1/me so the frontend can
    route the newly-registered master into their dashboard without a
    second network call.
    """
    tg_id = int(tg_user["id"])
    first_name = str(tg_user.get("first_name") or payload.name)

    # Reject re-registration — a tg_id that already owns a master or
    # salon should log in, not register again.
    existing = await session.scalar(select(Master).where(Master.tg_id == tg_id))
    if existing is not None:
        raise ApiError("already_registered", "already a master", status_code=409)
    salon_owner = await session.scalar(select(Salon).where(Salon.owner_tg_id == tg_id))
    if salon_owner is not None:
        raise ApiError("already_registered", "already a salon owner", status_code=409)

    slug = await _resolve_slug(session, payload.name, payload.slug)

    try:
        master = await MasterRegistrationService(session).register(
            tg_id=tg_id,
            name=payload.name.strip(),
            specialty=payload.specialty.strip(),
            slug=slug,
            lang=payload.lang,
            invite_code=payload.invite_code,
        )
    except SlugTaken as exc:
        raise ApiError("slug_taken", "slug already taken", status_code=409) from exc
    except InviteNotFound as exc:
        raise ApiError("invite_not_found", "invite not found", status_code=404) from exc
    except InviteAlreadyUsed as exc:
        raise ApiError("invite_used", "invite already used", status_code=409) from exc
    except InviteExpired as exc:
        raise ApiError("invite_expired", "invite expired", status_code=410) from exc

    await session.commit()
    track_event(
        tg_id,
        "master_registered",
        {"method": "invite", "slug": master.slug, "specialty": master.specialty_text or ""},
    )
    is_admin = tg_id in settings.admin_tg_ids
    return MeOut(
        role="master",
        profile=MeProfileOut(
            tg_id=tg_id,
            first_name=first_name,
            master_id=master.id,
            master_name=master.name,
            slug=master.slug,
            specialty=master.specialty_text or None,
        ),
        is_admin=is_admin,
        onboarded=master.onboarded_at is not None,
    )


@router.post("/salon/self", response_model=MeOut, status_code=201)
async def register_salon_self(
    payload: RegisterSalonSelfIn,
    tg_user: dict[str, Any] = Depends(require_tg_user),
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    app_bot: Bot | None = Depends(get_app_bot),
) -> MeOut:
    """Self-service salon registration — no invite required.

    Lands the salon as `is_public = true` immediately; no admin moderation step.
    """
    tg_id = int(tg_user["id"])
    first_name = str(tg_user.get("first_name") or payload.name)

    if await session.scalar(select(Salon).where(Salon.owner_tg_id == tg_id)):
        raise ApiError("already_registered", "already a salon owner", status_code=409)
    if await session.scalar(select(Master).where(Master.tg_id == tg_id)):
        raise ApiError("already_registered", "already a master", status_code=409)

    slug = await _resolve_slug(session, payload.name, payload.slug)

    try:
        salon = await SalonRepository(session).create(
            owner_tg_id=tg_id, name=payload.name.strip(), slug=slug
        )
    except IntegrityError as exc:
        raise ApiError("slug_taken", "slug already taken", status_code=409) from exc

    await session.commit()
    track_event(tg_id, "salon_registered", {"method": "self_service", "slug": salon.slug})
    await _notify_admins_of_new_signup(
        app_bot=app_bot,
        bot=bot,
        kind="salon",
        name=salon.name,
        slug=salon.slug,
        tg_id=tg_id,
        first_name=first_name,
    )
    is_admin = tg_id in settings.admin_tg_ids
    return MeOut(
        role="salon_owner",
        profile=MeProfileOut(
            tg_id=tg_id,
            first_name=first_name,
            salon_id=salon.id,
            salon_name=salon.name,
            slug=salon.slug,
        ),
        is_admin=is_admin,
    )


@router.post("/salon", response_model=MeOut, status_code=201)
async def register_salon(
    payload: RegisterSalonIn,
    tg_user: dict[str, Any] = Depends(require_tg_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    """Create a Salon row for the caller and redeem the salon_owner invite."""
    tg_id = int(tg_user["id"])
    first_name = str(tg_user.get("first_name") or payload.name)

    if await session.scalar(select(Salon).where(Salon.owner_tg_id == tg_id)):
        raise ApiError("already_registered", "already a salon owner", status_code=409)
    if await session.scalar(select(Master).where(Master.tg_id == tg_id)):
        raise ApiError("already_registered", "already a master", status_code=409)

    invite = await InviteRepository(session).by_code(payload.invite_code)
    if invite is None:
        raise ApiError("invite_not_found", "invite not found", status_code=404)
    if invite.kind != "salon_owner":
        raise ApiError("invite_wrong_kind", "wrong invite kind for salon", status_code=400)
    from datetime import UTC, datetime

    if invite.used_at is not None:
        raise ApiError("invite_used", "invite already used", status_code=409)
    if invite.expires_at <= datetime.now(UTC):
        raise ApiError("invite_expired", "invite expired", status_code=410)

    slug = await _resolve_slug(session, payload.name, payload.slug)

    try:
        salon = await SalonRepository(session).create(
            owner_tg_id=tg_id, name=payload.name.strip(), slug=slug
        )
    except IntegrityError as exc:
        raise ApiError("slug_taken", "slug already taken", status_code=409) from exc

    # Mark invite used — master_id points at the salon owner's bot-side
    # identity when there's no master yet, so we store the salon_id as
    # the "used_for_master_id" column's analogue in a dedicated column
    # would be cleaner, but the existing schema only tracks
    # used_for_master_id. Re-using is acceptable for salons since an
    # invite is one-shot.
    invite.used_by_tg_id = tg_id
    invite.used_at = datetime.now(UTC)

    await session.commit()
    is_admin = tg_id in settings.admin_tg_ids
    return MeOut(
        role="salon_owner",
        profile=MeProfileOut(
            tg_id=tg_id,
            first_name=first_name,
            salon_id=salon.id,
            salon_name=salon.name,
            slug=salon.slug,
        ),
        is_admin=is_admin,
    )


@router.post("/join-salon", response_model=MeOut)
async def join_salon(
    payload: JoinSalonIn,
    tg_user: dict[str, Any] = Depends(require_tg_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    """Existing master attaches themselves to a salon via that salon's
    invite code.

    Differs from `/register/master`: caller must already have a Master
    row. Errors out if they're already in a different salon — they have
    to leave that salon first (product decision: explicit moves only,
    no silent reassignment).
    """
    tg_id = int(tg_user["id"])
    first_name = str(tg_user.get("first_name") or "")

    master = await session.scalar(select(Master).where(Master.tg_id == tg_id))
    if master is None:
        raise ApiError("not_a_master", "register as a master first", status_code=400)

    invite = await InviteRepository(session).by_code(payload.invite_code)
    if invite is None:
        raise ApiError("invite_not_found", "invite not found", status_code=404)
    if invite.kind != "master":
        raise ApiError("invite_wrong_kind", "wrong invite kind", status_code=400)
    if invite.salon_id is None:
        raise ApiError("invite_no_salon", "invite is not salon-scoped", status_code=400)
    from datetime import UTC, datetime

    if invite.used_at is not None:
        raise ApiError("invite_used", "invite already used", status_code=409)
    if invite.expires_at <= datetime.now(UTC):
        raise ApiError("invite_expired", "invite expired", status_code=410)

    # Already in some salon? Block — let the master leave first.
    if master.salon_id is not None and master.salon_id != invite.salon_id:
        current_salon = await session.scalar(select(Salon).where(Salon.id == master.salon_id))
        raise ApiError(
            "already_in_salon",
            f"already in salon '{current_salon.name if current_salon else master.salon_id}'",
            status_code=409,
        )

    master.salon_id = invite.salon_id
    invite.used_by_tg_id = tg_id
    invite.used_for_master_id = master.id
    invite.used_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(master)

    is_admin = tg_id in settings.admin_tg_ids
    return MeOut(
        role="master",
        profile=MeProfileOut(
            tg_id=tg_id,
            first_name=first_name,
            master_id=master.id,
            master_name=master.name,
            slug=master.slug,
            specialty=master.specialty_text or None,
        ),
        is_admin=is_admin,
        onboarded=master.onboarded_at is not None,
    )
