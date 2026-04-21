from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment


class AppointmentRepository:
    """Appointment CRUD + day-scoped read for availability math."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active_for_day(
        self,
        master_id: UUID,
        *,
        day_start_utc: datetime,
        day_end_utc: datetime,
    ) -> list[Appointment]:
        """Appointments whose (start_at, end_at) overlaps [day_start, day_end) in UTC.

        Only `pending` and `confirmed` rows — cancelled/rejected/completed/no_show
        are excluded because they don't block the slot grid.
        """
        stmt = (
            select(Appointment)
            .where(
                Appointment.master_id == master_id,
                Appointment.status.in_(["pending", "confirmed"]),
                Appointment.start_at < day_end_utc,
                Appointment.end_at > day_start_utc,
            )
            .order_by(Appointment.start_at)
        )
        return list((await self._session.scalars(stmt)).all())

    async def list_active_for_month(
        self,
        master_id: UUID,
        *,
        month_start_utc: datetime,
        month_end_utc: datetime,
    ) -> list[Appointment]:
        """pending + confirmed appointments whose start_at lies in [month_start, month_end) UTC."""
        stmt = (
            select(Appointment)
            .where(
                Appointment.master_id == master_id,
                Appointment.status.in_(["pending", "confirmed"]),
                Appointment.start_at >= month_start_utc,
                Appointment.start_at < month_end_utc,
            )
            .order_by(Appointment.start_at)
        )
        return list((await self._session.scalars(stmt)).all())

    async def list_for_client(
        self,
        master_id: UUID,
        client_id: UUID,
        *,
        limit: int = 10,
        exclude_statuses: tuple[str, ...] = ("pending",),
    ) -> list[Appointment]:
        """Master-scoped history for one client, newest first, skipping pending by default."""
        stmt = (
            select(Appointment)
            .where(
                Appointment.master_id == master_id,
                Appointment.client_id == client_id,
            )
            .order_by(Appointment.start_at.desc())
            .limit(limit)
        )
        if exclude_statuses:
            stmt = stmt.where(Appointment.status.notin_(exclude_statuses))
        return list((await self._session.scalars(stmt)).all())

    async def get(
        self, appointment_id: UUID, *, master_id: UUID | None = None
    ) -> Appointment | None:
        stmt = select(Appointment).where(Appointment.id == appointment_id)
        if master_id is not None:
            stmt = stmt.where(Appointment.master_id == master_id)
        return cast(Appointment | None, await self._session.scalar(stmt))

    async def create(
        self,
        *,
        master_id: UUID,
        client_id: UUID,
        service_id: UUID,
        start_at: datetime,
        end_at: datetime,
        status: str,
        source: str,
        comment: str | None = None,
        decision_deadline: datetime | None = None,
        confirmed_at: datetime | None = None,
    ) -> Appointment:
        appt = Appointment(
            master_id=master_id,
            client_id=client_id,
            service_id=service_id,
            start_at=start_at,
            end_at=end_at,
            status=status,
            source=source,
            comment=comment,
            decision_deadline=decision_deadline,
            confirmed_at=confirmed_at,
        )
        self._session.add(appt)
        await self._session.flush()
        return appt

    async def update_status(
        self,
        appointment_id: UUID,
        *,
        status: str,
        master_id: UUID | None = None,
        confirmed_at: datetime | None = None,
        cancelled_at: datetime | None = None,
        cancelled_by: str | None = None,
    ) -> Appointment | None:
        appt = await self.get(appointment_id, master_id=master_id)
        if appt is None:
            return None
        appt.status = status
        if confirmed_at is not None:
            appt.confirmed_at = confirmed_at
        if cancelled_at is not None:
            appt.cancelled_at = cancelled_at
        if cancelled_by is not None:
            appt.cancelled_by = cancelled_by
        return appt

    async def get_pending_past_deadline(self, *, now: datetime) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(
                Appointment.status == "pending",
                Appointment.decision_deadline < now,
            )
            .order_by(Appointment.decision_deadline)
        )
        return list((await self._session.scalars(stmt)).all())
