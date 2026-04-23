from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Salon


class SalonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, owner_tg_id: int, name: str, slug: str) -> Salon:
        salon = Salon(owner_tg_id=owner_tg_id, name=name, slug=slug)
        self._session.add(salon)
        await self._session.flush()
        return salon

    async def by_id(self, salon_id: UUID) -> Salon | None:
        return cast(Salon | None, await self._session.get(Salon, salon_id))

    async def by_slug(self, slug: str) -> Salon | None:
        stmt = select(Salon).where(Salon.slug == slug)
        return cast(Salon | None, await self._session.scalar(stmt))

    async def by_owner_tg_id(self, tg_id: int) -> Salon | None:
        stmt = select(Salon).where(Salon.owner_tg_id == tg_id)
        return cast(Salon | None, await self._session.scalar(stmt))

    async def list_masters(self, salon_id: UUID) -> list[Master]:
        stmt = select(Master).where(Master.salon_id == salon_id).order_by(Master.name)
        return list((await self._session.scalars(stmt)).all())

    async def update_name(self, salon_id: UUID, name: str) -> None:
        salon = await self.by_id(salon_id)
        if salon is not None:
            salon.name = name

    async def update_slug(self, salon_id: UUID, slug: str) -> None:
        salon = await self.by_id(salon_id)
        if salon is not None:
            salon.slug = slug
