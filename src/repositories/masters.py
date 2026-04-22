from __future__ import annotations

from datetime import UTC
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

    async def update_lang(self, master_id: Any, lang: str) -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.lang = lang

    async def by_id(self, master_id: Any) -> Master | None:
        return cast(Master | None, await self._session.get(Master, master_id))

    async def by_slug(self, slug: str) -> Master | None:
        return cast(
            Master | None,
            await self._session.scalar(select(Master).where(Master.slug == slug)),
        )

    async def list_public(self) -> list[Master]:
        stmt = (
            select(Master)
            .where(Master.is_public.is_(True), Master.blocked_at.is_(None))
            .order_by(Master.created_at.asc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_all(self) -> list[Master]:
        stmt = select(Master).order_by(Master.created_at.asc())
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def update_slug(self, master_id: Any, slug: str) -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.slug = slug

    async def update_specialty(self, master_id: Any, specialty: str) -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.specialty_text = specialty

    async def update_name(self, master_id: Any, name: str) -> None:
        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.name = name

    async def set_blocked(self, master_id: Any, *, blocked: bool) -> None:
        from datetime import datetime

        master = await self._session.get(Master, master_id)
        if master is None:
            return
        master.blocked_at = datetime.now(UTC) if blocked else None
