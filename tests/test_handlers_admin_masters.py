from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.handlers.admin.masters import cmd_admin_master_detail, cmd_admin_masters


@pytest.mark.asyncio
async def test_empty_list(session: AsyncSession) -> None:
    message = AsyncMock()
    await cmd_admin_masters(message=message, session=session)
    message.answer.assert_awaited()
    text = message.answer.await_args[0][0]
    from src.strings import get_bundle
    ru = get_bundle("ru")
    assert ru.ADMIN_MASTERS_EMPTY in text


@pytest.mark.asyncio
async def test_list_shows_all_masters(session: AsyncSession) -> None:
    session.add(Master(tg_id=1, name="A", slug="a-0001"))
    session.add(Master(tg_id=2, name="B", slug="b-0001"))
    await session.commit()

    message = AsyncMock()
    await cmd_admin_masters(message=message, session=session)
    assert message.answer.await_count >= 1


@pytest.mark.asyncio
async def test_master_detail_by_slug(session: AsyncSession) -> None:
    session.add(Master(tg_id=1, name="A", slug="target-0001", specialty_text="Dentist"))
    await session.commit()

    message = AsyncMock()
    await cmd_admin_master_detail(
        message=message, session=session, slug="target-0001"
    )
    message.answer.assert_awaited()
    sent = message.answer.await_args[0][0]
    assert "target-0001" in sent
    assert "Dentist" in sent


@pytest.mark.asyncio
async def test_master_detail_not_found(session: AsyncSession) -> None:
    message = AsyncMock()
    await cmd_admin_master_detail(
        message=message, session=session, slug="nope"
    )
    message.answer.assert_awaited()
    from src.strings import get_bundle
    ru = get_bundle("ru")
    assert ru.ADMIN_MASTER_NOT_FOUND in message.answer.await_args[0][0]
