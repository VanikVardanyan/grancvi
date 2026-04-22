from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client
from src.repositories.appointments import AppointmentRepository
from src.repositories.masters import MasterRepository


@dataclass
class RejectedInfo:
    appointment_id: UUID
    client_tg_id: int | None


@dataclass
class BlockResult:
    rejected: list[RejectedInfo]


class ModerationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._masters = MasterRepository(session)
        self._appts = AppointmentRepository(session)

    async def block_master(self, master_id: UUID) -> BlockResult:
        """Block a master and bulk-reject all their pending appointments.

        Returns a BlockResult with RejectedInfo for each rejected appointment
        so the caller can notify affected clients.
        """
        await self._masters.set_blocked(master_id, blocked=True)
        rejected_appts = await self._appts.bulk_reject_pending_for_master(
            master_id, reason="master_blocked"
        )
        out: list[RejectedInfo] = []
        for appt in rejected_appts:
            client = await self._session.scalar(select(Client).where(Client.id == appt.client_id))
            out.append(
                RejectedInfo(
                    appointment_id=appt.id,
                    client_tg_id=client.tg_id if client else None,
                )
            )
        return BlockResult(rejected=out)

    async def unblock_master(self, master_id: UUID) -> None:
        """Clear the blocked_at timestamp for a master."""
        await self._masters.set_blocked(master_id, blocked=False)
