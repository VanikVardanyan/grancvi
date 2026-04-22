from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master
from src.handlers.master.new_invite import cmd_new_invite


@pytest.mark.asyncio
async def test_new_invite_creates_invite_and_sends_link(
    session: AsyncSession,
) -> None:
    master = Master(tg_id=101, name="A", slug="a-0001")
    session.add(master)
    await session.commit()

    message = AsyncMock()
    message.from_user = AsyncMock(id=101)

    with patch("src.handlers.master.new_invite.strings") as mocked_strings:
        mocked_strings.INVITE_CREATED_FMT = (
            "code: {code} link: {link} expires: {expires}"
        )
        await cmd_new_invite(message=message, session=session, master=master)
        await session.commit()

    from sqlalchemy import select
    invite = await session.scalar(
        select(Invite).where(Invite.created_by_tg_id == 101)
    )
    assert invite is not None
    message.answer.assert_awaited_once()
    sent = message.answer.await_args[0][0]
    assert invite.code in sent
    assert f"invite_{invite.code}" in sent
