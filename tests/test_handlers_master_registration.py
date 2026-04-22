from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite
from src.fsm.master_register import MasterRegister
from src.handlers.master.start import handle_start


@pytest.mark.asyncio
async def test_start_with_valid_invite_starts_registration(
    session: AsyncSession,
) -> None:
    invite = Invite(
        code="AAAA-BBBB", created_by_tg_id=1,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(invite)
    await session.commit()

    message = AsyncMock()
    message.text = "/start invite_AAAA-BBBB"
    message.from_user = AsyncMock(id=999)
    state = AsyncMock()

    await handle_start(
        message=message, master=None, state=state, session=session
    )
    state.set_state.assert_any_call(MasterRegister.waiting_lang)
    state.update_data.assert_any_call(invite_code="AAAA-BBBB")


@pytest.mark.asyncio
async def test_start_with_used_invite_shows_error(session: AsyncSession) -> None:
    from src.db.models import Master
    m = Master(tg_id=1, name="A", slug="a-0001")
    session.add(m)
    await session.flush()
    invite = Invite(
        code="USED-CODE", created_by_tg_id=1,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        used_by_tg_id=1, used_at=datetime.now(timezone.utc),
        used_for_master_id=m.id,
    )
    session.add(invite)
    await session.commit()

    message = AsyncMock()
    message.text = "/start invite_USED-CODE"
    message.from_user = AsyncMock(id=999)
    state = AsyncMock()

    await handle_start(
        message=message, master=None, state=state, session=session
    )
    message.answer.assert_awaited()
    sent = message.answer.await_args[0][0]
    from src.strings import get_bundle
    ru = get_bundle("ru")
    assert ru.INVITE_ALREADY_USED in sent
