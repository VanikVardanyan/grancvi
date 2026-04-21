from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.fsm.client_booking import ClientBooking
from src.keyboards.slots import services_pick_kb
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.strings import strings

router = Router(name="client_start")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


@router.message(CommandStart())
async def handle_start(
    message: Message,
    master: Master | None,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Entry point for any user whose tg_id is not the master's.

    The master's own `/start` is handled by `handlers/master/start.py` which runs
    before this router (master router is registered first). When this handler runs,
    `master` middleware value is always None by construction.
    """
    if master is not None:
        return  # master router should have caught it

    m_repo = MasterRepository(session)
    the_master = await m_repo.get_singleton()
    if the_master is None:
        await message.answer(strings.CLIENT_START_NO_MASTER)
        return

    s_repo = ServiceRepository(session)
    services = await s_repo.list_active(the_master.id)
    if not services:
        await message.answer(strings.CLIENT_NO_SERVICES)
        return

    await state.clear()
    await state.set_state(ClientBooking.ChoosingService)
    await state.update_data(master_id=str(the_master.id))
    await message.answer(strings.CLIENT_CHOOSE_SERVICE, reply_markup=services_pick_kb(services))
    log.info("client_start", tg_id=message.from_user.id if message.from_user else None)


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(strings.CLIENT_CANCELLED)
