from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite
from src.handlers.admin.invites_admin import cmd_admin_invites
from src.utils.time import now_utc


@pytest.mark.asyncio
async def test_admin_invites_lists_all(session: AsyncSession) -> None:
    now = now_utc()
    session.add(Invite(code="I1-0001", created_by_tg_id=1, expires_at=now + timedelta(days=7)))
    session.add(Invite(code="I2-0001", created_by_tg_id=2, expires_at=now + timedelta(days=7)))
    await session.commit()

    message = AsyncMock()
    await cmd_admin_invites(message=message, session=session)
    text = message.answer.await_args[0][0]
    assert "I1-0001" in text
    assert "I2-0001" in text
