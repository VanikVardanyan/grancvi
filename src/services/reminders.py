from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment
from src.repositories.reminders import ReminderRepository
from src.utils.time import now_utc

_OFFSETS: list[tuple[str, timedelta]] = [
    ("day_before", timedelta(hours=24)),
    ("two_hours", timedelta(hours=2)),
    ("master_before", timedelta(minutes=15)),
]


class ReminderService:
    """Plan + suppress `reminders` rows around appointment lifecycle events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ReminderRepository(session)

    async def schedule_for_appointment(
        self, appointment: Appointment, *, now: datetime | None = None
    ) -> int:
        n = now if now is not None else now_utc()
        rows: list[tuple[UUID, str, datetime]] = []
        for kind, offset in _OFFSETS:
            send_at = appointment.start_at - offset
            if send_at > n:
                rows.append((appointment.id, kind, send_at))
        return await self._repo.insert_many(rows)

    async def suppress_for_appointment(
        self, appointment_id: UUID, *, now: datetime | None = None
    ) -> int:
        n = now if now is not None else now_utc()
        return await self._repo.suppress_for_appointment(appointment_id, now=n)
