from __future__ import annotations

from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.services import ServiceAction, ServicePresetPick
from src.db.models import Master
from src.fsm.services import ServiceAdd, ServiceEditDuration, ServiceEditName
from src.keyboards.services import (
    edit_menu,
    service_presets_for,
    service_presets_kb,
    services_list,
)
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
async def cb_add(callback: CallbackQuery, state: FSMContext, master: Master | None) -> None:
    await state.set_state(ServiceAdd.waiting_name)
    await callback.answer()
    if callback.message is None or not hasattr(callback.message, "answer"):
        return
    specialty = (master.specialty_text if master is not None else "") or ""
    if service_presets_for(specialty):
        await callback.message.answer(
            strings.SERVICES_ADD_PICK_PRESET, reply_markup=service_presets_kb(specialty)
        )
    else:
        await callback.message.answer(strings.SERVICES_ADD_ASK_NAME)


@router.callback_query(ServicePresetPick.filter(), ServiceAdd.waiting_name)
async def cb_pick_preset(
    callback: CallbackQuery,
    callback_data: ServicePresetPick,
    state: FSMContext,
    master: Master | None,
) -> None:
    await callback.answer()
    if callback_data.key == "custom":
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(strings.SERVICES_ADD_ASK_NAME)
        return
    label_key = callback_data.key.upper()
    name: str | None = getattr(strings, f"SERVICE_PRESET_{label_key}", None)
    if name is None:
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(strings.SERVICES_ADD_ASK_NAME)
        return
    await state.update_data(name=name)
    await state.set_state(ServiceAdd.waiting_duration)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.SERVICES_ADD_ASK_DURATION)


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


@router.callback_query(ServiceAction.filter(F.action == "edit"))
async def cb_edit(callback: CallbackQuery, callback_data: ServiceAction) -> None:
    if callback_data.service_id is None:
        await callback.answer()
        return
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.SERVICES_EDIT_MENU, reply_markup=edit_menu(callback_data.service_id)
        )


@router.callback_query(ServiceAction.filter(F.action == "delete"))
async def cb_delete(
    callback: CallbackQuery,
    callback_data: ServiceAction,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None or callback_data.service_id is None:
        await callback.answer()
        return
    repo = ServiceRepository(session)
    await repo.set_active(callback_data.service_id, master_id=master.id, active=False)
    await callback.answer(strings.SERVICES_DELETED)
    if isinstance(callback.message, Message):
        await _render_list(callback.message, master, session)


@router.callback_query(ServiceAction.filter(F.action == "toggle"))
async def cb_toggle(
    callback: CallbackQuery,
    callback_data: ServiceAction,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None or callback_data.service_id is None:
        await callback.answer()
        return
    repo = ServiceRepository(session)
    svc = await repo.get(callback_data.service_id, master_id=master.id)
    if svc is None:
        await callback.answer()
        return
    await repo.set_active(svc.id, master_id=master.id, active=not svc.active)
    await callback.answer(strings.SERVICES_UPDATED)


@router.callback_query(ServiceAction.filter(F.action == "edit_name"))
async def cb_edit_name(
    callback: CallbackQuery,
    callback_data: ServiceAction,
    state: FSMContext,
) -> None:
    if callback_data.service_id is None:
        await callback.answer()
        return
    await state.set_state(ServiceEditName.waiting_name)
    await state.update_data(service_id=str(callback_data.service_id))
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.SERVICES_EDIT_NAME_PROMPT)


@router.message(ServiceEditName.waiting_name)
async def handle_edit_name(
    message: Message,
    state: FSMContext,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await state.clear()
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer(strings.SERVICES_EDIT_NAME_PROMPT)
        return
    data = await state.get_data()
    service_id = UUID(data["service_id"])
    repo = ServiceRepository(session)
    await repo.update(service_id, master_id=master.id, name=name)
    await state.clear()
    await message.answer(strings.SERVICES_UPDATED)
    await _render_list(message, master, session)


@router.callback_query(ServiceAction.filter(F.action == "edit_duration"))
async def cb_edit_duration(
    callback: CallbackQuery,
    callback_data: ServiceAction,
    state: FSMContext,
) -> None:
    if callback_data.service_id is None:
        await callback.answer()
        return
    await state.set_state(ServiceEditDuration.waiting_duration)
    await state.update_data(service_id=str(callback_data.service_id))
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.SERVICES_EDIT_DURATION_PROMPT)


@router.message(ServiceEditDuration.waiting_duration)
async def handle_edit_duration(
    message: Message,
    state: FSMContext,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await state.clear()
        return
    try:
        duration = int((message.text or "").strip())
    except ValueError:
        await message.answer(strings.SERVICES_ADD_BAD_DURATION)
        return
    if duration <= 0:
        await message.answer(strings.SERVICES_ADD_BAD_DURATION)
        return
    data = await state.get_data()
    service_id = UUID(data["service_id"])
    repo = ServiceRepository(session)
    await repo.update(service_id, master_id=master.id, duration_min=duration)
    await state.clear()
    await message.answer(strings.SERVICES_UPDATED)
    await _render_list(message, master, session)


@router.callback_query(ServiceAction.filter(F.action == "back"))
async def cb_back(callback: CallbackQuery, master: Master | None, session: AsyncSession) -> None:
    if master is None:
        await callback.answer()
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        await _render_list(callback.message, master, session)
