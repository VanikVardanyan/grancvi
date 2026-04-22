from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.handlers.client.catalog import render_catalog


@pytest.mark.asyncio
async def test_empty_catalog_sends_empty_message(session: AsyncSession) -> None:
    message = AsyncMock()
    await render_catalog(message=message, session=session)
    message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_catalog_lists_public_masters(session: AsyncSession) -> None:
    m1 = Master(tg_id=1, name="A", slug="a-0001", specialty_text="Dentist", is_public=True)
    m2 = Master(tg_id=2, name="B", slug="b-0001", specialty_text="Nails", is_public=True)
    session.add_all([m1, m2])
    await session.commit()

    message = AsyncMock()
    await render_catalog(message=message, session=session)
    message.answer.assert_awaited_once()
    call = message.answer.await_args
    assert call.kwargs.get("reply_markup") is not None
