from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_admin
from src.api.deps import get_session
from src.api.schemas import AdminMasterOut, AdminStatsOut
from src.db.models import Appointment, Client, Master
from src.utils.time import now_utc

router = APIRouter(prefix="/v1/admin", tags=["admin"])


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
