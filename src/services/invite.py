from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite
from src.exceptions import InviteAlreadyUsed, InviteExpired, InviteNotFound
from src.repositories.invites import InviteRepository

_ALPHABET: Final[str] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I,O,0,1
_TTL_DAYS: Final[int] = 7


class InviteService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = InviteRepository(session)

    @staticmethod
    def generate_code() -> str:
        left = "".join(secrets.choice(_ALPHABET) for _ in range(4))
        right = "".join(secrets.choice(_ALPHABET) for _ in range(4))
        return f"{left}-{right}"

    async def create_invite(self, *, actor_tg_id: int) -> Invite:
        code = self.generate_code()
        expires = datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS)
        return await self._repo.create(
            code=code, created_by_tg_id=actor_tg_id, expires_at=expires
        )

    async def redeem(self, *, code: str, tg_id: int, master_id: UUID) -> Invite:
        invite = await self._repo.by_code(code)
        if invite is None:
            raise InviteNotFound(code)
        if invite.used_at is not None:
            raise InviteAlreadyUsed(code)
        if invite.expires_at <= datetime.now(timezone.utc):
            raise InviteExpired(code)
        await self._repo.mark_used(
            code=code,
            used_by_tg_id=tg_id,
            master_id=master_id,
            used_at=datetime.now(timezone.utc),
        )
        await self._session.flush()
        refreshed = await self._repo.by_code(code)
        assert refreshed is not None
        return refreshed
