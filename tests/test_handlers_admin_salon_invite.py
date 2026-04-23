from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite


@pytest.mark.asyncio
async def test_admin_invite_salon_creates_salon_owner_kind(session: AsyncSession) -> None:
    from src.handlers.admin.invites_admin import cb_admin_new_salon

    cb = AsyncMock()
    cb.from_user = MagicMock(id=747967837)
    cb.message = MagicMock(spec=Message)
    cb.message.answer = AsyncMock()

    await cb_admin_new_salon(callback=cb, session=session)

    invites = list((await session.scalars(select(Invite))).all())
    assert len(invites) == 1
    assert invites[0].kind == "salon_owner"
    assert invites[0].created_by_tg_id == 747967837
    assert invites[0].salon_id is None
