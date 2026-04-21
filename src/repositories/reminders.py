from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Reminder, Service


class ReminderRepository:
    """CRUD for `reminders` rows + join-query for the sender worker."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert_many(self, rows: list[tuple[UUID, str, datetime]]) -> int:
        """Insert reminders, skipping rows that already exist (idempotent).

        Returns the number of rows actually inserted.
        """
        if not rows:
            return 0
        stmt = (
            pg_insert(Reminder)
            .values(
                [
                    {"appointment_id": appt_id, "kind": kind, "send_at": send_at}
                    for appt_id, kind, send_at in rows
                ]
            )
            .on_conflict_do_nothing(index_elements=["appointment_id", "kind"])
        )
        result = cast(CursorResult[tuple[()]], await self._session.execute(stmt))
        return int(result.rowcount or 0)

    async def get_due_for_update(
        self, *, now: datetime, limit: int = 100
    ) -> list[tuple[Reminder, Appointment, Master, Client, Service]]:
        """Fetch unsent reminders due by `now`, joined with appointment context.

        Uses FOR UPDATE SKIP LOCKED to allow concurrent workers without contention.
        """
        stmt = (
            select(Reminder, Appointment, Master, Client, Service)
            .join(Appointment, Reminder.appointment_id == Appointment.id)
            .join(Master, Appointment.master_id == Master.id)
            .join(Client, Appointment.client_id == Client.id)
            .join(Service, Appointment.service_id == Service.id)
            .where(Reminder.sent.is_(False), Reminder.send_at <= now)
            .order_by(Reminder.send_at)
            .limit(limit)
            .with_for_update(of=Reminder, skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return cast(
            list[tuple[Reminder, Appointment, Master, Client, Service]],
            [tuple(row) for row in result.all()],
        )

    async def mark_sent(self, reminder_id: UUID, *, sent_at: datetime) -> None:
        """Mark a single reminder as sent."""
        stmt = update(Reminder).where(Reminder.id == reminder_id).values(sent=True, sent_at=sent_at)
        await self._session.execute(stmt)

    async def suppress_for_appointment(self, appointment_id: UUID, *, now: datetime) -> int:
        """Mark all unsent reminders for an appointment as sent (suppressed).

        Returns the number of rows updated.
        """
        stmt = (
            update(Reminder)
            .where(
                Reminder.appointment_id == appointment_id,
                Reminder.sent.is_(False),
            )
            .values(sent=True, sent_at=now)
        )
        result = cast(CursorResult[tuple[()]], await self._session.execute(stmt))
        return int(result.rowcount or 0)
