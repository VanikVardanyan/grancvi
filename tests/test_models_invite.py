from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite


@pytest.mark.asyncio
async def test_invite_can_be_created(session: AsyncSession) -> None:
    invite = Invite(
        code="A7K2-X9MP",
        created_by_tg_id=111,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(invite)
    await session.commit()
    assert invite.id is not None
    assert invite.used_at is None
    assert invite.used_by_tg_id is None
    assert invite.used_for_master_id is None


@pytest.mark.asyncio
async def test_invite_code_is_unique(session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    i1 = Invite(
        code="DUP-CODE",
        created_by_tg_id=111,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(i1)
    await session.commit()

    i2 = Invite(
        code="DUP-CODE",
        created_by_tg_id=222,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(i2)
    with pytest.raises(IntegrityError):
        await session.commit()
