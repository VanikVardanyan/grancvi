from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_salon
from src.api.deps import get_session
from src.api.errors import ApiError
from src.api.schemas import (
    AdminInviteOut,
    OkOut,
    SalonAppointmentOut,
    SalonMasterOut,
    SalonProfileOut,
)
from src.config import settings
from src.db.models import Appointment, Client, Master, Salon, Service
from src.repositories.invites import InviteRepository
from src.utils.time import now_utc

router = APIRouter(prefix="/v1/salon/me", tags=["salon"])


_VISIBLE_STATUSES: frozenset[str] = frozenset({"pending", "confirmed", "completed", "no_show"})


def _invite_link(code: str) -> str:
    return f"https://t.me/{settings.bot_username}?start=invite_{code}"


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
