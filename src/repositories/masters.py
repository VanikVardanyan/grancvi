from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master


class MasterRepository:
    """CRUD for Master."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_tg_id(self, tg_id: int) -> Master | None:
        return cast(
            Master | None,
            await self._session.scalar(select(Master).where(Master.tg_id == tg_id)),
        )

    async def get_singleton(self) -> Master | None:
        """Return the single master of v0.1.

        If the invariant is violated, return the earliest-created row so the
        choice is deterministic. v0.2 (multi-tenant) will replace this with a
        short_id lookup.
        """
        stmt = select(Master).order_by(Master.created_at).limit(1)
        return cast(Master | None, await self._session.scalar(stmt))

    async def create(
        self,
        *,
        tg_id: int,
        name: str,
        phone: str | None = None,
        timezone: str = "Asia/Yerevan",
        lang: str = "ru",
    ) -> Master:
        master = Master(tg_id=tg_id, name=name, phone=phone, timezone=timezone, lang=lang)
        self._session.add(master)
        await self._session.flush()
        return master

    async def update_work_hours(self, master_id: Any, work_hours: dict[str, Any]) -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.work_hours = work_hours

    async def update_breaks(self, master_id: Any, breaks: dict[str, Any]) -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.breaks = breaks
