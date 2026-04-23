from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_master
from src.api.deps import get_session
from src.api.errors import ApiError
from src.api.schemas import MasterAppointmentOut
from src.db.models import Appointment, Client, Master, Service

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
