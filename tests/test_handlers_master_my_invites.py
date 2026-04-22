from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master
from src.handlers.master.my_invites import cmd_myinvites


@pytest.mark.asyncio
async def test_empty_sends_empty_msg(session: AsyncSession) -> None:
    master = Master(tg_id=1, name="A", slug="a-0001")
    session.add(master)
    await session.commit()
    message = AsyncMock()
    await cmd_myinvites(message=message, session=session, master=master)
    message.answer.assert_awaited_once()
    text = message.answer.await_args[0][0]
    from src.strings import get_bundle

    ru = get_bundle("ru")
    assert ru.MY_INVITES_EMPTY in text


@pytest.mark.asyncio
async def test_lists_invites_with_status(session: AsyncSession) -> None:
    master = Master(tg_id=1, name="A", slug="a-0001")
    session.add(master)
    await session.flush()
    now = datetime.now(UTC)
    session.add(Invite(code="ACT-0001", created_by_tg_id=1, expires_at=now + timedelta(days=1)))
    session.add(Invite(code="EXP-0001", created_by_tg_id=1, expires_at=now - timedelta(days=1)))
    session.add(
        Invite(
            code="USD-0001",
            created_by_tg_id=1,
            expires_at=now + timedelta(days=1),
            used_by_tg_id=555,
            used_at=now,
            used_for_master_id=master.id,
        )
    )
    await session.commit()

    message = AsyncMock()
    await cmd_myinvites(message=message, session=session, master=master)
    text = message.answer.await_args[0][0]
    assert "ACT-0001" in text
    assert "EXP-0001" in text
    assert "USD-0001" in text
