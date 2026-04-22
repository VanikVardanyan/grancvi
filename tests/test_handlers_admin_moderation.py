from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.handlers.admin.moderation import cmd_block_master, cmd_unblock_master
from src.utils.time import now_utc


@pytest.mark.asyncio
async def test_block_sends_notifications_and_blocks(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="target-0001")
    session.add(m)
    await session.flush()
    svc = Service(master_id=m.id, name="cut", duration_min=30)
    cli = Client(master_id=m.id, name="C", phone="+111", tg_id=987654)
    session.add_all([svc, cli])
    await session.flush()
    now = now_utc()
    session.add(
        Appointment(
            master_id=m.id,
            client_id=cli.id,
            service_id=svc.id,
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2),
            status="pending",
            source="client_request",
        )
    )
    await session.commit()

    message = AsyncMock()
    bot = AsyncMock()
    await cmd_block_master(message=message, session=session, slug="target-0001", bot=bot)
    await session.commit()

    bot.send_message.assert_awaited()
    await session.refresh(m)
    assert m.blocked_at is not None


@pytest.mark.asyncio
async def test_unblock_clears(session: AsyncSession) -> None:
    m = Master(
        tg_id=1,
        name="A",
        slug="target-0001",
        blocked_at=now_utc(),
    )
    session.add(m)
    await session.commit()

    message = AsyncMock()
    await cmd_unblock_master(message=message, session=session, slug="target-0001")
    await session.commit()

    await session.refresh(m)
    assert m.blocked_at is None


@pytest.mark.asyncio
async def test_block_master_not_found(session: AsyncSession) -> None:
    message = AsyncMock()
    bot = AsyncMock()
    await cmd_block_master(message=message, session=session, slug="missing-9999", bot=bot)
    from src.strings import get_bundle

    ru = get_bundle("ru")
    message.answer.assert_awaited_once_with(ru.ADMIN_MASTER_NOT_FOUND)
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_unblock_master_not_found(session: AsyncSession) -> None:
    message = AsyncMock()
    await cmd_unblock_master(message=message, session=session, slug="missing-9999")
    from src.strings import get_bundle

    ru = get_bundle("ru")
    message.answer.assert_awaited_once_with(ru.ADMIN_MASTER_NOT_FOUND)
