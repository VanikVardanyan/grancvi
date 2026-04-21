from __future__ import annotations

from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.client_services import ClientServicePick
from src.callback_data.master_add import (
    PhoneDupCallback,
    RecentClientCallback,
)
from src.db.models import Client, Master
from src.fsm.master_add import MasterAdd
from src.keyboards.calendar import calendar_keyboard
from src.keyboards.master_add import phone_dup_kb, recent_clients_kb, search_results_kb
from src.keyboards.slots import services_pick_kb
from src.repositories.clients import ClientRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.strings import strings
from src.utils.phone import normalize as normalize_phone
from src.utils.time import now_utc

router = Router(name="master_add_manual")
log: structlog.stdlib.BoundLogger = structlog.get_logger()

_MIN_NAME = 2
_MIN_SEARCH = 2


@router.message(Command("add"))
async def cmd_add(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    repo = ClientRepository(session)
    clients = await repo.list_recent_by_master(master.id)
    text = strings.MANUAL_PICK_CLIENT if clients else strings.MANUAL_NO_RECENT
    await state.clear()
    await state.set_state(MasterAdd.PickingClient)
    await message.answer(text, reply_markup=recent_clients_kb(clients))


@router.callback_query(RecentClientCallback.filter(), MasterAdd.PickingClient)
@router.callback_query(RecentClientCallback.filter(), MasterAdd.SearchingClient)
async def cb_pick_recent(
    callback: CallbackQuery,
    callback_data: RecentClientCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    if callback_data.client_id == "new":
        await state.set_state(MasterAdd.NewClientName)
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(strings.MANUAL_ASK_NAME)
        return
    if callback_data.client_id == "search":
        await state.set_state(MasterAdd.SearchingClient)
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(strings.MANUAL_SEARCH_PROMPT)
        return

    # Concrete UUID
    try:
        picked_id = UUID(callback_data.client_id)
    except ValueError:
        await callback.answer("Bad id", show_alert=True)
        return
    await state.update_data(client_id=str(picked_id))
    await _show_services(state, session, master, reply_to=callback.message)


async def _show_services(
    state: FSMContext, session: AsyncSession, master: Master, *, reply_to: Any
) -> None:
    services = await ServiceRepository(session).list_active(master_id=master.id)
    await state.set_state(MasterAdd.PickingService)
    if reply_to is not None and hasattr(reply_to, "answer"):
        await reply_to.answer(strings.MANUAL_ASK_SERVICE, reply_markup=services_pick_kb(services))


@router.message(MasterAdd.SearchingClient)
async def msg_search_query(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    q = (message.text or "").strip()
    if len(q) < _MIN_SEARCH:
        await message.answer(strings.MANUAL_SEARCH_PROMPT)
        return
    repo = ClientRepository(session)
    results = await repo.search_by_master(master.id, q)
    if not results:
        await message.answer(strings.MANUAL_SEARCH_EMPTY)
        return
    await message.answer(strings.MANUAL_PICK_CLIENT, reply_markup=search_results_kb(results))


@router.callback_query(F.data == "master_add_search_cancel", MasterAdd.SearchingClient)
async def cb_search_cancel(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, master: Master
) -> None:
    await callback.answer()
    repo = ClientRepository(session)
    clients = await repo.list_recent_by_master(master.id)
    await state.set_state(MasterAdd.PickingClient)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_PICK_CLIENT, reply_markup=recent_clients_kb(clients)
        )


@router.message(MasterAdd.NewClientName)
async def msg_new_client_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < _MIN_NAME:
        await message.answer(strings.MANUAL_NAME_BAD)
        return
    await state.update_data(pending_name=name)
    await state.set_state(MasterAdd.NewClientPhone)
    await message.answer(strings.MANUAL_ASK_PHONE)


@router.message(MasterAdd.NewClientPhone)
async def msg_new_client_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    raw = (message.text or "").strip()
    normalized = normalize_phone(raw)
    if normalized is None:
        await message.answer(strings.MANUAL_PHONE_BAD)
        return
    data = await state.get_data()
    name = data.get("pending_name", "")
    repo = ClientRepository(session)
    # Check for existing (master_id, phone)
    from sqlalchemy import select  # local import to keep file imports focused

    existing = await session.scalar(
        select(Client).where(Client.master_id == master.id, Client.phone == normalized)
    )
    if existing is not None:
        await state.update_data(pending_phone=normalized)
        await message.answer(
            strings.MANUAL_PHONE_DUP.format(name=existing.name),
            reply_markup=phone_dup_kb(existing.id),
        )
        return
    created = await repo.upsert_by_phone(
        master_id=master.id, phone=normalized, name=name, tg_id=None
    )
    await session.commit()
    await state.update_data(client_id=str(created.id))
    await state.set_state(MasterAdd.PickingService)
    await _show_services(state, session, master, reply_to=message)


@router.callback_query(PhoneDupCallback.filter(), MasterAdd.NewClientPhone)
async def cb_phone_dup(
    callback: CallbackQuery,
    callback_data: PhoneDupCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    if callback_data.action == "use":
        await state.update_data(client_id=str(callback_data.client_id))
        await _show_services(state, session, master, reply_to=callback.message)
        return
    # retry: drop pending_phone, prompt again
    data = await state.get_data()
    data.pop("pending_phone", None)
    await state.set_data(data)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.MANUAL_ASK_PHONE)


@router.callback_query(ClientServicePick.filter(), MasterAdd.PickingService)
async def cb_pick_service(
    callback: CallbackQuery,
    callback_data: ClientServicePick,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    s_repo = ServiceRepository(session)
    service = await s_repo.get(callback_data.service_id, master_id=master.id)
    if service is None:
        await callback.answer("Service missing", show_alert=True)
        return
    await state.update_data(service_id=str(service.id))
    await state.set_state(MasterAdd.PickingDate)

    tz = ZoneInfo(master.timezone)
    today = now_utc().astimezone(tz).date()
    month = today.replace(day=1)
    loads = await BookingService(session).get_month_load(
        master=master, service=service, month=month, now=now_utc()
    )
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_ASK_DATE,
            reply_markup=calendar_keyboard(month=month, loads=loads, today=today),
        )
