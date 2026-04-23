from __future__ import annotations

import re
from collections.abc import Iterable
from typing import cast
from uuid import UUID

from sqlalchemy import desc, func, nulls_last, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client


class ClientRepository:
    """CRUD for Client scoped by (master_id, phone) uniqueness."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, client_id: UUID) -> Client | None:
        return cast(Client | None, await self._session.get(Client, client_id))

    async def create_anonymous(
        self,
        *,
        master_id: UUID,
        name: str,
        tg_id: int | None = None,
    ) -> Client:
        """Create a phone-less client (master-side walk-in).

        Each call produces a new row — no dedup, since there's no stable key
        without a phone.
        """
        client = Client(master_id=master_id, phone=None, name=name, tg_id=tg_id)
        self._session.add(client)
        await self._session.flush()
        return client

    async def upsert_by_phone(
        self,
        *,
        master_id: UUID,
        phone: str,
        name: str,
        tg_id: int | None,
    ) -> Client:
        """Find existing (master_id, phone) row or create one.

        Updates `name` and `tg_id` if the row exists; `tg_id=None` does NOT
        overwrite an existing value (so a later anonymous booking by phone
        doesn't forget the Telegram linkage).
        """
        stmt = select(Client).where(Client.master_id == master_id, Client.phone == phone)
        existing = await self._session.scalar(stmt)
        if existing is None:
            client = Client(master_id=master_id, phone=phone, name=name, tg_id=tg_id)
            self._session.add(client)
            await self._session.flush()
            return client
        existing.name = name
        if tg_id is not None:
            existing.tg_id = tg_id
        return existing

    async def list_recent_by_master(self, master_id: UUID, *, limit: int = 10) -> list[Client]:
        """Clients ordered by their most recent appointment with this master.

        Clients without any appointments come last, ordered by `created_at DESC`.
        """
        last_appt = func.max(Appointment.start_at).label("last_appt")
        stmt = (
            select(Client)
            .outerjoin(
                Appointment,
                (Appointment.client_id == Client.id) & (Appointment.master_id == master_id),
            )
            .where(Client.master_id == master_id)
            .group_by(Client.id)
            .order_by(nulls_last(desc(last_appt)), desc(Client.created_at))
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())

    async def search_by_master(
        self, master_id: UUID, query: str, *, limit: int = 10
    ) -> list[Client]:
        """Substring search by name (ILIKE) and by digit-only phone.

        Queries shorter than 2 characters return an empty list. `query` is
        stripped; digits in `query` are matched against the phone stripped
        of its own non-digit characters.
        """
        q = query.strip()
        if len(q) < 2:
            return []
        digits = re.sub(r"\D", "", q)

        phone_digits = func.regexp_replace(Client.phone, r"\D", "", "g")
        like_pattern = f"%{q}%"
        digit_pattern = f"%{digits}%"

        conditions = [Client.name.ilike(like_pattern)]
        if digits:
            conditions.append(phone_digits.like(digit_pattern))

        stmt = (
            select(Client)
            .where(Client.master_id == master_id, or_(*conditions))
            .order_by(Client.name)
            .limit(limit)
        )
        return list((await self._session.scalars(stmt)).all())

    async def get_names_by_ids(self, client_ids: Iterable[UUID]) -> dict[UUID, str]:
        """Return {client_id: name} map for the given IDs (empty input → empty dict)."""
        ids = list(client_ids)
        if not ids:
            return {}
        stmt = select(Client.id, Client.name).where(Client.id.in_(ids))
        rows = await self._session.execute(stmt)
        return {row.id: row.name for row in rows}

    async def update_notes(self, client_id: UUID, notes: str | None) -> None:
        """Set `Client.notes`. Empty string or None → stored as NULL."""
        client = await self.get(client_id)
        if client is None:
            return
        cleaned = notes.strip() if notes else None
        client.notes = cleaned if cleaned else None
