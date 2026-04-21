from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client


class ClientRepository:
    """CRUD for Client scoped by (master_id, phone) uniqueness."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, client_id: UUID) -> Client | None:
        return cast(Client | None, await self._session.get(Client, client_id))

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
