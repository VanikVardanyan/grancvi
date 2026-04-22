from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite


class InviteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        code: str,
        created_by_tg_id: int,
        expires_at: datetime,
    ) -> Invite:
        invite = Invite(
            code=code,
            created_by_tg_id=created_by_tg_id,
            expires_at=expires_at,
        )
        self._session.add(invite)
        await self._session.flush()
        return invite

    async def by_code(self, code: str) -> Invite | None:
        return cast(
            Invite | None,
            await self._session.scalar(select(Invite).where(Invite.code == code)),
        )

    async def mark_used(
        self,
        *,
        code: str,
        used_by_tg_id: int,
        master_id: UUID,
        used_at: datetime,
    ) -> None:
        invite = await self.by_code(code)
        if invite is None:
            return
        invite.used_by_tg_id = used_by_tg_id
        invite.used_for_master_id = master_id
        invite.used_at = used_at

    async def list_by_creator(self, tg_id: int) -> list[Invite]:
        stmt = (
            select(Invite)
            .where(Invite.created_by_tg_id == tg_id)
            .order_by(Invite.created_at.desc())
        )
        result = await self._session.scalars(stmt)
        return list(result.all())

    async def list_all(self) -> list[Invite]:
        stmt = select(Invite).order_by(Invite.created_at.desc())
        result = await self._session.scalars(stmt)
        return list(result.all())
