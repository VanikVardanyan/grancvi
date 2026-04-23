from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Salon
from src.fsm.salon_register import SalonRegister


async def _mkctx() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))


@pytest.mark.asyncio
async def test_start_with_salon_owner_invite_enters_registration(
    session: AsyncSession,
) -> None:
    from src.handlers.salon.start import handle_salon_start

    session.add(
        Invite(
            code="salown1",
            created_by_tg_id=1,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            kind="salon_owner",
        )
    )
    await session.commit()

    msg = AsyncMock()
    msg.text = "/start invite_salown1"
    msg.from_user = MagicMock(id=500)
    state = await _mkctx()

    await handle_salon_start(message=msg, salon=None, state=state, session=session)
    assert await state.get_state() == SalonRegister.waiting_lang.state


@pytest.mark.asyncio
async def test_start_as_registered_salon_owner_shows_main_menu(
    session: AsyncSession,
) -> None:
    from src.handlers.salon.start import handle_salon_start

    salon = Salon(owner_tg_id=777, name="S", slug="ss-1")
    session.add(salon)
    await session.commit()

    msg = AsyncMock()
    msg.text = "/start"
    msg.from_user = MagicMock(id=777)
    state = await _mkctx()

    await handle_salon_start(message=msg, salon=salon, state=state, session=session)
    msg.answer.assert_awaited()
