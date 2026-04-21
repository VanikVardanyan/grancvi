from __future__ import annotations

from collections.abc import Iterable
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Service


class ServiceRepository:
    """CRUD for Service (a master's offered treatments)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_names_by_ids(self, service_ids: Iterable[UUID]) -> dict[UUID, str]:
        """Return {service_id: name} map for the given IDs (empty input → empty dict)."""
        ids = list(service_ids)
        if not ids:
            return {}
        stmt = select(Service.id, Service.name).where(Service.id.in_(ids))
        rows = await self._session.execute(stmt)
        return {row.id: row.name for row in rows}

    async def list_active(self, master_id: UUID) -> list[Service]:
        stmt = (
            select(Service)
            .where(Service.master_id == master_id, Service.active.is_(True))
            .order_by(Service.position, Service.created_at)
        )
        return list((await self._session.scalars(stmt)).all())

    async def get(self, service_id: UUID, *, master_id: UUID) -> Service | None:
        stmt = select(Service).where(Service.id == service_id, Service.master_id == master_id)
        return cast(Service | None, await self._session.scalar(stmt))

    async def create(self, *, master_id: UUID, name: str, duration_min: int) -> Service:
        service = Service(master_id=master_id, name=name, duration_min=duration_min)
        self._session.add(service)
        await self._session.flush()
        return service

    async def update(
        self,
        service_id: UUID,
        *,
        master_id: UUID,
        name: str | None = None,
        duration_min: int | None = None,
    ) -> Service | None:
        service = await self.get(service_id, master_id=master_id)
        if service is None:
            return None
        if name is not None:
            service.name = name
        if duration_min is not None:
            service.duration_min = duration_min
        return service

    async def set_active(
        self, service_id: UUID, *, master_id: UUID, active: bool
    ) -> Service | None:
        service = await self.get(service_id, master_id=master_id)
        if service is None:
            return None
        service.active = active
        return service
