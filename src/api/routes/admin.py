from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_admin
from src.api.deps import get_session
from src.api.errors import ApiError
from src.api.schemas import (
    AdminAppointmentOut,
    AdminInviteCreateIn,
    AdminInviteOut,
    AdminMasterDetailOut,
    AdminMasterOut,
    AdminSalonOut,
    AdminStatsOut,
    OkOut,
    SpecialtyCreateIn,
    SpecialtyOut,
    SpecialtyUpdateIn,
)
from src.config import settings
from src.db.models import Appointment, Client, Master, Salon, Service, Specialty
from src.repositories.invites import InviteRepository
from src.repositories.masters import MasterRepository
from src.services.moderation import ModerationService
from src.utils.time import now_utc

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _invite_link(code: str) -> str:
    # Point new invites at the TMA launcher bot — the in-TMA /register
    # page handles the flow so the user never has to chat with the
    # legacy bot.
    return f"https://t.me/{settings.app_bot_username}?start=invite_{code}"


@router.get("/stats", response_model=AdminStatsOut)
async def admin_stats(
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminStatsOut:
    now = now_utc()
    masters_active = (
        await session.scalar(select(func.count(Master.id)).where(Master.blocked_at.is_(None))) or 0
    )
    masters_blocked = (
        await session.scalar(select(func.count(Master.id)).where(Master.blocked_at.is_not(None)))
        or 0
    )
    clients_distinct = (
        await session.scalar(
            select(func.count(distinct(Client.tg_id))).where(Client.tg_id.is_not(None))
        )
        or 0
    )
    appt_7d = (
        await session.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.created_at >= now - timedelta(days=7)
            )
        )
        or 0
    )
    appt_30d = (
        await session.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.created_at >= now - timedelta(days=30)
            )
        )
        or 0
    )
    return AdminStatsOut(
        masters_active=masters_active,
        masters_blocked=masters_blocked,
        clients=clients_distinct,
        appointments_7d=appt_7d,
        appointments_30d=appt_30d,
    )


@router.get("/masters", response_model=list[AdminMasterOut])
async def admin_masters(
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AdminMasterOut]:
    """All masters with per-master appointment counters, newest first."""
    now = now_utc()
    cutoff = now - timedelta(days=30)

    total_sq = (
        select(Appointment.master_id, func.count(Appointment.id).label("total"))
        .group_by(Appointment.master_id)
        .subquery()
    )
    last30_sq = (
        select(Appointment.master_id, func.count(Appointment.id).label("last30"))
        .where(Appointment.created_at >= cutoff)
        .group_by(Appointment.master_id)
        .subquery()
    )

    stmt = (
        select(
            Master,
            func.coalesce(total_sq.c.total, 0),
            func.coalesce(last30_sq.c.last30, 0),
        )
        .outerjoin(total_sq, total_sq.c.master_id == Master.id)
        .outerjoin(last30_sq, last30_sq.c.master_id == Master.id)
        .order_by(Master.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        AdminMasterOut(
            id=m.id,
            name=m.name,
            slug=m.slug,
            specialty=m.specialty_text or "",
            tg_id=m.tg_id,
            is_public=m.is_public,
            blocked=m.blocked_at is not None,
            created_at=m.created_at,
            appointments_total=int(total),
            appointments_30d=int(last30),
        )
        for (m, total, last30) in rows
    ]


@router.get("/masters/{master_id}", response_model=AdminMasterDetailOut)
async def admin_master_detail(
    master_id: UUID,
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminMasterDetailOut:
    """Drill-down view: master profile fields + last 50 appointments
    with client/service names joined for display.
    """
    master = await MasterRepository(session).by_id(master_id)
    if master is None:
        raise ApiError("not_found", "master not found", status_code=404)

    now = now_utc()
    cutoff = now - timedelta(days=30)

    total_count = await session.scalar(
        select(func.count(Appointment.id)).where(Appointment.master_id == master_id)
    )
    last30_count = await session.scalar(
        select(func.count(Appointment.id)).where(
            Appointment.master_id == master_id,
            Appointment.created_at >= cutoff,
        )
    )
    services_count = await session.scalar(
        select(func.count(Service.id)).where(
            Service.master_id == master_id,
            Service.active.is_(True),
        )
    )

    appt_rows = (
        await session.execute(
            select(
                Appointment.id,
                Appointment.start_at,
                Appointment.end_at,
                Appointment.status,
                Appointment.source,
                Client.name,
                Client.phone,
                Service.name.label("service_name"),
            )
            .join(Client, Client.id == Appointment.client_id)
            .join(Service, Service.id == Appointment.service_id)
            .where(Appointment.master_id == master_id)
            .order_by(Appointment.start_at.desc())
            .limit(50)
        )
    ).all()

    return AdminMasterDetailOut(
        id=master.id,
        name=master.name,
        slug=master.slug,
        specialty=master.specialty_text or "",
        tg_id=master.tg_id,
        phone=master.phone,
        phone_public=master.phone_public,
        lang=master.lang,
        is_public=master.is_public,
        blocked=master.blocked_at is not None,
        created_at=master.created_at,
        onboarded_at=master.onboarded_at,
        slot_step_min=master.slot_step_min,
        auto_confirm=master.auto_confirm,
        services_count=int(services_count or 0),
        appointments_total=int(total_count or 0),
        appointments_30d=int(last30_count or 0),
        recent_appointments=[
            AdminAppointmentOut(
                id=row.id,
                start_at=row.start_at,
                end_at=row.end_at,
                status=row.status,
                source=row.source,
                client_name=row.name,
                client_phone=row.phone,
                service_name=row.service_name,
            )
            for row in appt_rows
        ],
    )


@router.post("/masters/{master_id}/block", response_model=OkOut)
async def admin_block_master(
    master_id: UUID,
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> OkOut:
    """Block a master (sets blocked_at, rejects open appointments).

    Client-facing notifications of rejected appointments — handled by the
    bot-side flow when an admin triggers block there. From the TMA we
    currently skip the per-client notify; appointments become rejected
    in-DB and the client sees it on their next check.
    """
    if (await MasterRepository(session).by_id(master_id)) is None:
        raise ApiError("not_found", "master not found", status_code=404)
    await ModerationService(session).block_master(master_id)
    await session.commit()
    return OkOut(ok=True)


@router.post("/masters/{master_id}/unblock", response_model=OkOut)
async def admin_unblock_master(
    master_id: UUID,
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> OkOut:
    if (await MasterRepository(session).by_id(master_id)) is None:
        raise ApiError("not_found", "master not found", status_code=404)
    await ModerationService(session).unblock_master(master_id)
    await session.commit()
    return OkOut(ok=True)


@router.get("/salons", response_model=list[AdminSalonOut])
async def admin_salons(
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[AdminSalonOut]:
    """All salons with the count of masters attached, newest first."""
    masters_sq = (
        select(Master.salon_id, func.count(Master.id).label("cnt"))
        .where(Master.salon_id.is_not(None))
        .group_by(Master.salon_id)
        .subquery()
    )
    stmt = (
        select(Salon, func.coalesce(masters_sq.c.cnt, 0))
        .outerjoin(masters_sq, masters_sq.c.salon_id == Salon.id)
        .order_by(Salon.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        AdminSalonOut(
            id=s.id,
            name=s.name,
            slug=s.slug,
            owner_tg_id=s.owner_tg_id,
            masters_count=int(cnt),
            created_at=s.created_at,
            is_public=s.is_public,
        )
        for (s, cnt) in rows
    ]


@router.delete("/salons/{salon_id}", response_model=OkOut)
async def admin_delete_salon(
    salon_id: UUID,
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> OkOut:
    """Hard-delete a salon. Masters' salon_id flips to NULL via the FK
    (they keep working as standalone). Salon-scoped invites cascade
    away. The owner_tg_id frees up so the same Telegram account can be
    re-invited as either kind.
    """
    salon = await session.scalar(select(Salon).where(Salon.id == salon_id))
    if salon is None:
        raise ApiError("not_found", "salon not found", status_code=404)
    await session.delete(salon)
    await session.commit()
    return OkOut(ok=True)


@router.delete("/masters/{master_id}", response_model=OkOut)
async def admin_delete_master(
    master_id: UUID,
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> OkOut:
    """Hard-delete a master and everything dangling off them.

    DB-level ON DELETE CASCADE on services / clients / appointments /
    reminders does the cleanup. invites.used_for_master_id flips to
    NULL — the used flag stays so the same invite can't be reused.
    Frees up the tg_id so the user can re-register from scratch.
    """
    master = await MasterRepository(session).by_id(master_id)
    if master is None:
        raise ApiError("not_found", "master not found", status_code=404)
    await session.delete(master)
    await session.commit()
    return OkOut(ok=True)


@router.post("/invites", response_model=AdminInviteOut, status_code=201)
async def admin_create_invite(
    payload: AdminInviteCreateIn,
    admin_user: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminInviteOut:
    """Create an invite code for a new master or salon owner.

    Returned `link` is a `t.me/<bot>?start=invite_<code>` deep link the
    admin can share with the invitee.
    """
    repo = InviteRepository(session)
    invite = await repo.create(
        created_by_tg_id=int(admin_user["id"]),
        kind=payload.kind,
    )
    await session.commit()
    return AdminInviteOut(
        code=invite.code,
        kind=invite.kind,
        link=_invite_link(invite.code),
        expires_at=invite.expires_at,
    )


@router.post("/specialties", response_model=SpecialtyOut, status_code=201)
async def admin_create_specialty(
    payload: SpecialtyCreateIn,
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SpecialtyOut:
    """Add a new profession. `code` must be unique and snake_case."""
    existing = await session.scalar(select(Specialty).where(Specialty.code == payload.code))
    if existing is not None:
        raise ApiError("code_taken", "specialty code already exists", status_code=409)
    sp = Specialty(
        code=payload.code,
        name_ru=payload.name_ru,
        name_hy=payload.name_hy,
        position=payload.position,
    )
    session.add(sp)
    await session.commit()
    return SpecialtyOut(code=sp.code, name_ru=sp.name_ru, name_hy=sp.name_hy, position=sp.position)


@router.patch("/specialties/{code}", response_model=SpecialtyOut)
async def admin_update_specialty(
    code: str,
    payload: SpecialtyUpdateIn,
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> SpecialtyOut:
    sp = await session.scalar(select(Specialty).where(Specialty.code == code))
    if sp is None:
        raise ApiError("not_found", "specialty not found", status_code=404)
    if payload.name_ru is not None:
        sp.name_ru = payload.name_ru
    if payload.name_hy is not None:
        sp.name_hy = payload.name_hy
    if payload.position is not None:
        sp.position = payload.position
    await session.commit()
    return SpecialtyOut(code=sp.code, name_ru=sp.name_ru, name_hy=sp.name_hy, position=sp.position)


@router.delete("/specialties/{code}", response_model=OkOut)
async def admin_delete_specialty(
    code: str,
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> OkOut:
    """Delete a profession. Existing masters keep the legacy code in
    their specialty_text — UI renders it as raw text since the lookup
    fails. Use update instead of delete if you want the rename to flow.
    """
    sp = await session.scalar(select(Specialty).where(Specialty.code == code))
    if sp is None:
        raise ApiError("not_found", "specialty not found", status_code=404)
    await session.delete(sp)
    await session.commit()
    return OkOut(ok=True)


@router.post("/masters/{master_id}/approve", response_model=OkOut)
async def admin_approve_master(
    master_id: UUID,
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> OkOut:
    """Mark a self-registered master as moderated → flips is_public=true.
    Idempotent — re-approving an already-public master is a no-op.
    """
    m = await MasterRepository(session).by_id(master_id)
    if m is None:
        raise ApiError("not_found", "master not found", status_code=404)
    if not m.is_public:
        m.is_public = True
        await session.commit()
    return OkOut(ok=True)


@router.post("/salons/{salon_id}/approve", response_model=OkOut)
async def admin_approve_salon(
    salon_id: UUID,
    _: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> OkOut:
    """Mark a self-registered salon as moderated → flips is_public=true."""
    s = await session.scalar(select(Salon).where(Salon.id == salon_id))
    if s is None:
        raise ApiError("not_found", "salon not found", status_code=404)
    if not s.is_public:
        s.is_public = True
        await session.commit()
    return OkOut(ok=True)
