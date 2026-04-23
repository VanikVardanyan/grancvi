from __future__ import annotations

from datetime import UTC
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Service
from src.handlers.client.start import handle_start


@pytest.mark.asyncio
async def test_valid_master_slug_starts_booking(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="anna-0001", is_public=True)
    session.add(m)
    await session.flush()
    session.add(Service(master_id=m.id, name="cut", duration_min=30))
    await session.commit()

    message = AsyncMock()
    message.text = "/start master_anna-0001"
    message.from_user = AsyncMock(id=999)
    state = AsyncMock()

    await handle_start(message=message, master=None, state=state, session=session)
    state.update_data.assert_any_call(master_id=str(m.id))


@pytest.mark.asyncio
async def test_unknown_slug_shows_catalog(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="anna-0001", is_public=True)
    session.add(m)
    await session.commit()

    message = AsyncMock()
    message.text = "/start master_nope"
    message.from_user = AsyncMock(id=999)
    state = AsyncMock()

    await handle_start(message=message, master=None, state=state, session=session)
    message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_blocked_master_not_bookable(session: AsyncSession) -> None:
    from datetime import datetime

    m = Master(
        tg_id=1,
        name="A",
        slug="blocked-0001",
        blocked_at=datetime.now(UTC),
        is_public=True,
    )
    session.add(m)
    await session.commit()

    message = AsyncMock()
    message.text = "/start master_blocked-0001"
    message.from_user = AsyncMock(id=999)
    state = AsyncMock()

    await handle_start(message=message, master=None, state=state, session=session)
    for call in state.update_data.await_args_list:
        assert "master_id" not in call.kwargs


@pytest.mark.asyncio
async def test_master_can_book_with_other_master_via_deep_link(session: AsyncSession) -> None:
    """A registered master opening another master's deep link enters the client
    booking flow targeting that master (master_id of the target, not self)."""
    from src.handlers.master.start import handle_start as master_handle_start

    self_master = Master(tg_id=100, name="Me", slug="me-0001", is_public=True)
    other_master = Master(tg_id=200, name="Other", slug="other-0001", is_public=True)
    session.add_all([self_master, other_master])
    await session.flush()
    session.add(Service(master_id=other_master.id, name="cleaning", duration_min=30))
    await session.commit()

    message = AsyncMock()
    message.text = "/start master_other-0001"
    message.from_user = AsyncMock(id=100)
    state = AsyncMock()

    await master_handle_start(message=message, master=self_master, state=state, session=session)
    state.update_data.assert_any_call(master_id=str(other_master.id))


@pytest.mark.asyncio
async def test_master_opening_own_deep_link_gets_welcome_back(session: AsyncSession) -> None:
    """A master scanning their own QR/link just sees the welcome-back menu,
    not a booking flow targeting themselves."""
    from src.handlers.master.start import handle_start as master_handle_start

    me = Master(tg_id=100, name="Me", slug="me-0001", is_public=True)
    session.add(me)
    await session.commit()

    message = AsyncMock()
    message.text = "/start master_me-0001"
    message.from_user = AsyncMock(id=100)
    state = AsyncMock()

    await master_handle_start(message=message, master=me, state=state, session=session)
    for call in state.update_data.await_args_list:
        assert "master_id" not in call.kwargs
