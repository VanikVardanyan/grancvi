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
    AdminInviteCreateIn,
    AdminInviteOut,
    AdminMasterOut,
    AdminStatsOut,
    OkOut,
)
from src.config import settings
from src.db.models import Appointment, Client, Master
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
