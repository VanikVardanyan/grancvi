from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.catalog import CatalogMasterCallback
from src.fsm.client_booking import ClientBooking
from src.keyboards.catalog import catalog_kb
from src.keyboards.slots import services_pick_kb
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.strings import strings

router = Router(name="client_catalog")


async def render_catalog(*, message: Message, session: AsyncSession) -> None:
    repo = MasterRepository(session)
    masters = await repo.list_public()
    if not masters:
        await message.answer(strings.CLIENT_CATALOG_EMPTY)
        return
    await message.answer(
        strings.CLIENT_CATALOG_HEADER, reply_markup=catalog_kb(masters)
    )


@router.callback_query(CatalogMasterCallback.filter())
async def on_catalog_pick(
    cb: CallbackQuery,
    callback_data: CatalogMasterCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await cb.answer()
    repo = MasterRepository(session)
    master = await repo.by_id(callback_data.master_id)
    if master is None or master.blocked_at is not None:
        if cb.message is not None:
            await cb.message.answer(strings.CLIENT_MASTER_NOT_FOUND)
        return
    s_repo = ServiceRepository(session)
    services = await s_repo.list_active(master.id)
    if not services:
        if cb.message is not None:
            await cb.message.answer(strings.CLIENT_NO_SERVICES)
        return
    await state.clear()
    await state.set_state(ClientBooking.ChoosingService)
    await state.update_data(master_id=str(master.id))
    if cb.message is not None:
        await cb.message.answer(
            strings.CLIENT_CHOOSE_SERVICE, reply_markup=services_pick_kb(services)
        )
