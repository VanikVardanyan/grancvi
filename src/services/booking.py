from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Service
from src.repositories.appointments import AppointmentRepository
from src.services.availability import calculate_free_slots


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
