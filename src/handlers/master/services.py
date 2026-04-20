from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.services import ServiceAction
from src.db.models import Master
from src.fsm.services import ServiceAdd
from src.keyboards.services import services_list
from src.repositories.services import ServiceRepository
from src.strings import strings

router = Router(name="master_services")


async def _render_list(
    target: Message,
    master: Master,
    session: AsyncSession,
) -> None:
    repo = ServiceRepository(session)
    svcs = await repo.list_active(master.id)
    if not svcs:
        await target.answer(strings.SERVICES_EMPTY, reply_markup=services_list([]))
        return
    await target.answer(strings.SERVICES_LIST_TITLE, reply_markup=services_list(svcs))


@router.message(Command("services"))
async def cmd_services(message: Message, master: Master | None, session: AsyncSession) -> None:
    if master is None:
        return
    await _render_list(message, master, session)


@router.callback_query(ServiceAction.filter(F.action == "add"))
async def cb_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ServiceAdd.waiting_name)
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.SERVICES_ADD_ASK_NAME)


@router.message(ServiceAdd.waiting_name)
async def add_handle_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(strings.SERVICES_ADD_ASK_NAME)
        return
    await state.update_data(name=name)
    await state.set_state(ServiceAdd.waiting_duration)
    await message.answer(strings.SERVICES_ADD_ASK_DURATION)


@router.message(ServiceAdd.waiting_duration)
async def add_handle_duration(
    message: Message,
    state: FSMContext,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await state.clear()
        return
    raw = (message.text or "").strip()
    try:
        duration = int(raw)
    except ValueError:
        await message.answer(strings.SERVICES_ADD_BAD_DURATION)
        return
    if duration <= 0:
        await message.answer(strings.SERVICES_ADD_BAD_DURATION)
        return

    data = await state.get_data()
    name: str = data["name"]
    repo = ServiceRepository(session)
    await repo.create(master_id=master.id, name=name, duration_min=duration)

    await state.clear()
    await message.answer(strings.SERVICES_ADDED)
    await _render_list(message, master, session)
