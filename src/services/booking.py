from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.exceptions import InvalidState, NotFound, SlotAlreadyTaken
from src.repositories.appointments import AppointmentRepository
from src.services.availability import calculate_free_slots
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
