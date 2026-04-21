from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.exceptions import InvalidState, NotFound, SlotAlreadyTaken
from src.repositories.appointments import AppointmentRepository
from src.services.availability import calculate_day_loads, calculate_free_slots
from src.utils.time import now_utc


class BookingService:
    """Appointment lifecycle + slot lookup.

    Owns its own commit/rollback on the create paths (`create_pending`,
    `create_manual`) so that the partial unique index on appointments can
    arbitrate concurrent callers via IntegrityError. All other methods
    mutate in-place and rely on the DB middleware to commit on success.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AppointmentRepository(session)

    async def get_free_slots(
        self,
        master: Master,
        service: Service,
        day: date,
        *,
        now: datetime | None = None,
    ) -> list[datetime]:
        tz = ZoneInfo(master.timezone)
        day_start_local = datetime(day.year, day.month, day.day, tzinfo=tz)
        day_start_utc = day_start_local.astimezone(UTC)
        day_end_utc = (day_start_local + timedelta(days=1)).astimezone(UTC)
        appts = await self._repo.list_active_for_day(
            master.id, day_start_utc=day_start_utc, day_end_utc=day_end_utc
        )
        booked = [(a.start_at, a.end_at) for a in appts]
        return calculate_free_slots(
            work_hours=master.work_hours,
            breaks=master.breaks,
            booked=booked,
            day=day,
            tz=tz,
            slot_step_min=master.slot_step_min,
            service_duration_min=service.duration_min,
            now=now,
        )

    async def create_pending(
        self,
        *,
        master: Master,
        client: Client,
        service: Service,
        start_at: datetime,
        now: datetime | None = None,
    ) -> Appointment:
        """Create a client-requested appointment in `pending` state.

        Commits on success so the unique-index row lock is released for other
        writers. On IntegrityError (slot taken between `get_free_slots` and here),
        rolls back and raises SlotAlreadyTaken — handler should re-render the grid.
        """
        n = now if now is not None else now_utc()
        end_at = start_at + timedelta(minutes=service.duration_min)
        deadline = n + timedelta(minutes=master.decision_timeout_min)
        try:
            appt = await self._repo.create(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at=start_at,
                end_at=end_at,
                status="pending",
                source="client_request",
                decision_deadline=deadline,
            )
            await self._session.commit()
            return appt
        except IntegrityError as exc:
            await self._session.rollback()
            raise SlotAlreadyTaken(str(start_at)) from exc

    async def confirm(
        self,
        appointment_id: UUID,
        *,
        master_id: UUID,
        now: datetime | None = None,
    ) -> Appointment:
        n = now if now is not None else now_utc()
        appt = await self._repo.get(appointment_id, master_id=master_id)
        if appt is None:
            raise NotFound(str(appointment_id))
        if appt.status != "pending":
            raise InvalidState(f"cannot confirm from status={appt.status!r}")
        appt.status = "confirmed"
        appt.confirmed_at = n
        return appt

    async def reject(
        self,
        appointment_id: UUID,
        *,
        master_id: UUID,
        reason: str | None = None,
    ) -> Appointment:
        appt = await self._repo.get(appointment_id, master_id=master_id)
        if appt is None:
            raise NotFound(str(appointment_id))
        if appt.status != "pending":
            raise InvalidState(f"cannot reject from status={appt.status!r}")
        appt.status = "rejected"
        if reason:
            appt.comment = reason if not appt.comment else f"{appt.comment}\n{reason}"
        return appt

    async def cancel(
        self,
        appointment_id: UUID,
        *,
        cancelled_by: str,
        now: datetime | None = None,
    ) -> Appointment:
        if cancelled_by not in ("client", "master", "system"):
            raise ValueError(f"invalid cancelled_by: {cancelled_by!r}")
        n = now if now is not None else now_utc()
        appt = await self._repo.get(appointment_id)
        if appt is None:
            raise NotFound(str(appointment_id))
        if appt.status in ("cancelled", "rejected", "completed", "no_show"):
            raise InvalidState(f"cannot cancel from status={appt.status!r}")
        appt.status = "cancelled"
        appt.cancelled_at = n
        appt.cancelled_by = cancelled_by
        return appt

    async def create_manual(
        self,
        *,
        master: Master,
        client: Client,
        service: Service,
        start_at: datetime,
        comment: str | None = None,
        now: datetime | None = None,
    ) -> Appointment:
        """Master-added appointment — instantly `confirmed`.

        Same commit/rollback behaviour as `create_pending` so the partial unique
        index enforces mutual exclusion with concurrent client requests.
        """
        n = now if now is not None else now_utc()
        end_at = start_at + timedelta(minutes=service.duration_min)
        try:
            appt = await self._repo.create(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at=start_at,
                end_at=end_at,
                status="confirmed",
                source="master_manual",
                comment=comment,
                confirmed_at=n,
            )
            await self._session.commit()
            return appt
        except IntegrityError as exc:
            await self._session.rollback()
            raise SlotAlreadyTaken(str(start_at)) from exc

    async def get_month_load(
        self,
        *,
        master: Master,
        service: Service,
        month: date,
        now: datetime | None = None,
    ) -> dict[date, int]:
        """Return free-slot counts per day of `month` (see calculate_day_loads)."""
        n = now if now is not None else now_utc()
        tz = ZoneInfo(master.timezone)
        month_start_local = datetime(month.year, month.month, 1, tzinfo=tz)
        month_end_local = datetime(
            month.year + (month.month // 12),
            (month.month % 12) + 1,
            1,
            tzinfo=tz,
        )
        month_start_utc = month_start_local.astimezone(UTC)
        month_end_utc = month_end_local.astimezone(UTC)

        appts = await self._repo.list_active_for_month(
            master.id,
            month_start_utc=month_start_utc,
            month_end_utc=month_end_utc,
        )

        booked_by_day: dict[date, list[tuple[datetime, datetime]]] = defaultdict(list)
        for a in appts:
            local_day = a.start_at.astimezone(tz).date()
            booked_by_day[local_day].append((a.start_at, a.end_at))

        return calculate_day_loads(
            work_hours=master.work_hours,
            breaks=master.breaks,
            booked_by_day=dict(booked_by_day),
            month=month,
            tz=tz,
            slot_step_min=master.slot_step_min,
            service_duration_min=service.duration_min,
            now=n,
        )

    async def list_client_history(
        self,
        master: Master,
        client_id: UUID,
        *,
        limit: int = 10,
    ) -> list[Appointment]:
        """Master-scoped recent history for a client (excludes pending)."""
        return await self._repo.list_for_client(master.id, client_id, limit=limit)
