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


@pytest.mark.asyncio
async def test_admin_invites_empty(session: AsyncSession) -> None:
    message = AsyncMock()
    await cmd_admin_invites(message=message, session=session)
    from src.strings import get_bundle

    ru = get_bundle("ru")
    message.answer.assert_awaited_once()
    args, _kwargs = message.answer.await_args
    assert args[0] == ru.MY_INVITES_EMPTY


@pytest.mark.asyncio
async def test_admin_invites_shows_expired_status(session: AsyncSession) -> None:
    past = now_utc() - timedelta(days=1)
    session.add(Invite(code="EXP-0001", created_by_tg_id=1, expires_at=past))
    await session.commit()

    message = AsyncMock()
    await cmd_admin_invites(message=message, session=session)
    text = message.answer.await_args[0][0]
    from src.strings import get_bundle

    ru = get_bundle("ru")
    assert "EXP-0001" in text
    assert ru.MY_INVITES_STATUS_EXPIRED in text


@pytest.mark.asyncio
async def test_admin_invites_shows_used_status(session: AsyncSession) -> None:
    from src.db.models import Master
    from src.strings import get_bundle

    master = Master(tg_id=100, name="U", slug="u-0001")
    session.add(master)
    await session.flush()

    future = now_utc() + timedelta(days=7)
    session.add(
        Invite(
            code="USED-0001",
            created_by_tg_id=1,
            expires_at=future,
            used_at=now_utc(),
            used_by_tg_id=100,
            used_for_master_id=master.id,
        )
    )
    await session.commit()

    message = AsyncMock()
    await cmd_admin_invites(message=message, session=session)
    text = message.answer.await_args[0][0]
    ru = get_bundle("ru")
    assert "USED-0001" in text
    assert ru.MY_INVITES_STATUS_USED in text
