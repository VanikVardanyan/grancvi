from __future__ import annotations

import re as _re
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.calendar import CalendarCallback
from src.callback_data.client_services import ClientServicePick
from src.callback_data.master_add import (
    CustomTimeCallback,
    PhoneDupCallback,
    RecentClientCallback,
    SkipCommentCallback,
    SkipPhoneCallback,
)
from src.callback_data.slots import SlotCallback
from src.db.models import Client, Master, Service
from src.exceptions import SlotAlreadyTaken
from src.fsm.master_add import MasterAdd
from src.keyboards.calendar import calendar_keyboard
from src.keyboards.master_add import (
    client_cancel_kb,
    confirm_add_kb,
    phone_dup_kb,
    recent_clients_kb,
    search_results_kb,
    skip_comment_kb,
    skip_phone_kb,
    slots_grid_with_custom,
)
from src.keyboards.slots import services_pick_kb
from src.repositories.clients import ClientRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.services.reminders import ReminderService
from src.strings import strings
from src.utils.phone import normalize as normalize_phone
from src.utils.time import now_utc

router = Router(name="master_add_manual")
log: structlog.stdlib.BoundLogger = structlog.get_logger()

_MIN_NAME = 2
_MIN_SEARCH = 2

_CUSTOM_FULL_RE = _re.compile(r"^(\d{1,2})\.(\d{1,2})\s+(\d{1,2}):(\d{2})$")
_CUSTOM_TIME_RE = _re.compile(r"^(\d{1,2}):(\d{2})$")
_COMMENT_MAX = 200


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
    await message.answer(strings.MANUAL_ASK_PHONE, reply_markup=skip_phone_kb())


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
        await callback.message.answer(strings.MANUAL_ASK_PHONE, reply_markup=skip_phone_kb())


@router.callback_query(SkipPhoneCallback.filter(), MasterAdd.NewClientPhone)
async def cb_skip_phone(
    callback: CallbackQuery,
    callback_data: SkipPhoneCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    data = await state.get_data()
    name = data.get("pending_name", "")
    repo = ClientRepository(session)
    client = await repo.create_anonymous(master_id=master.id, name=name)
    await session.commit()
    await state.update_data(client_id=str(client.id))
    await state.set_state(MasterAdd.PickingService)
    reply_to = callback.message if isinstance(callback.message, Message) else None
    if reply_to is not None:
        await _show_services(state, session, master, reply_to=reply_to)


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


# --- Part B: date/slot/custom/comment/confirm ---


@router.callback_query(CalendarCallback.filter(), MasterAdd.PickingDate)
async def cb_pick_date(
    callback: CallbackQuery,
    callback_data: CalendarCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    if callback_data.action == "noop":
        return

    data = await state.get_data()
    service_id = UUID(data["service_id"])
    service = await ServiceRepository(session).get(service_id, master_id=master.id)
    if service is None:
        await state.clear()
        return

    tz = ZoneInfo(master.timezone)
    today = now_utc().astimezone(tz).date()
    svc = BookingService(session)

    if callback_data.action == "nav":
        month = date(callback_data.year, callback_data.month, 1)
        loads = await svc.get_month_load(master=master, service=service, month=month, now=now_utc())
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(
                strings.MANUAL_ASK_DATE,
                reply_markup=calendar_keyboard(month=month, loads=loads, today=today),
            )
        return

    # pick
    picked = date(callback_data.year, callback_data.month, callback_data.day)
    slots = await svc.get_free_slots(master, service, picked, now=now_utc())
    await state.update_data(date=picked.isoformat())
    await state.set_state(MasterAdd.PickingSlot)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_ASK_SLOT, reply_markup=slots_grid_with_custom(slots, tz=tz)
        )


@router.callback_query(SlotCallback.filter(), MasterAdd.PickingSlot)
async def cb_pick_slot(
    callback: CallbackQuery,
    callback_data: SlotCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    data = await state.get_data()
    picked = date.fromisoformat(data["date"])
    tz = ZoneInfo(master.timezone)
    local_start = datetime(
        picked.year, picked.month, picked.day, callback_data.hour, callback_data.minute, tzinfo=tz
    )
    start_at_utc = local_start.astimezone(UTC)
    await state.update_data(start_at=start_at_utc.isoformat())
    await state.set_state(MasterAdd.EnteringComment)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.MANUAL_ASK_COMMENT, reply_markup=skip_comment_kb())


@router.callback_query(CustomTimeCallback.filter(), MasterAdd.PickingSlot)
async def cb_custom_time(
    callback: CallbackQuery,
    callback_data: CustomTimeCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    await state.set_state(MasterAdd.EnteringCustomTime)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.MANUAL_CUSTOM_PROMPT)


@router.callback_query(F.data == "master_add_back", MasterAdd.PickingSlot)
async def cb_back_to_date(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, master: Master
) -> None:
    await callback.answer()
    data = await state.get_data()
    service_id = UUID(data["service_id"])
    service = await ServiceRepository(session).get(service_id, master_id=master.id)
    if service is None:
        await state.clear()
        return
    tz = ZoneInfo(master.timezone)
    today = now_utc().astimezone(tz).date()
    month = today.replace(day=1)
    loads = await BookingService(session).get_month_load(
        master=master, service=service, month=month, now=now_utc()
    )
    await state.set_state(MasterAdd.PickingDate)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_ASK_DATE,
            reply_markup=calendar_keyboard(month=month, loads=loads, today=today),
        )


@router.message(MasterAdd.EnteringCustomTime)
async def msg_custom_time(
    message: Message,
    state: FSMContext,
    master: Master,
) -> None:
    raw = (message.text or "").strip()
    tz = ZoneInfo(master.timezone)
    data = await state.get_data()
    current_date = date.fromisoformat(data["date"]) if data.get("date") else None

    m_full = _CUSTOM_FULL_RE.match(raw)
    m_time = _CUSTOM_TIME_RE.match(raw)

    if m_full:
        dd, mm, hh, mi = (int(g) for g in m_full.groups())
        today = now_utc().astimezone(tz).date()
        year = today.year
        try:
            picked = date(year, mm, dd)
        except ValueError:
            await message.answer(strings.MANUAL_CUSTOM_BAD)
            return
        # If the resulting date is already in the past, assume next year.
        if picked < today:
            try:
                picked = date(year + 1, mm, dd)
            except ValueError:
                await message.answer(strings.MANUAL_CUSTOM_BAD)
                return
        hour, minute = hh, mi
    elif m_time and current_date is not None:
        hour, minute = (int(g) for g in m_time.groups())
        picked = current_date
    else:
        await message.answer(strings.MANUAL_CUSTOM_BAD)
        return

    if not (0 <= hour < 24 and 0 <= minute < 60):
        await message.answer(strings.MANUAL_CUSTOM_BAD)
        return

    local = datetime(picked.year, picked.month, picked.day, hour, minute, tzinfo=tz)
    start_at_utc = local.astimezone(UTC)
    if start_at_utc <= now_utc():
        await message.answer(strings.MANUAL_CUSTOM_PAST)
        return

    await state.update_data(date=picked.isoformat(), start_at=start_at_utc.isoformat())
    await state.set_state(MasterAdd.EnteringComment)
    await message.answer(strings.MANUAL_ASK_COMMENT, reply_markup=skip_comment_kb())


def _render_confirm(
    *, client: Client, service: Service, start_at: datetime, comment: str | None, tz: ZoneInfo
) -> str:
    local = start_at.astimezone(tz)
    text: str = strings.MANUAL_CONFIRM_CARD.format(
        client=client.name,
        phone=(client.phone or "—"),
        service=service.name,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        notes=(comment or "—"),
    )
    return text


async def _load_client_service(
    session: AsyncSession, master: Master, data: dict[str, Any]
) -> tuple[Client | None, Service | None]:
    client = await session.get(Client, UUID(data["client_id"]))
    service = await ServiceRepository(session).get(UUID(data["service_id"]), master_id=master.id)
    return client, service


@router.message(MasterAdd.EnteringComment)
async def msg_comment(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    raw = (message.text or "").strip()[:_COMMENT_MAX]
    data = await state.get_data()
    client, service = await _load_client_service(session, master, data)
    if client is None or service is None:
        await state.clear()
        return
    await state.update_data(comment=raw or None)
    await state.set_state(MasterAdd.Confirming)
    tz = ZoneInfo(master.timezone)
    start_at = datetime.fromisoformat(data["start_at"])
    await message.answer(
        _render_confirm(
            client=client, service=service, start_at=start_at, comment=raw or None, tz=tz
        ),
        reply_markup=confirm_add_kb(),
    )


@router.callback_query(SkipCommentCallback.filter(), MasterAdd.EnteringComment)
async def cb_skip_comment(
    callback: CallbackQuery,
    callback_data: SkipCommentCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    data = await state.get_data()
    client, service = await _load_client_service(session, master, data)
    if client is None or service is None:
        await state.clear()
        return
    await state.update_data(comment=None)
    await state.set_state(MasterAdd.Confirming)
    tz = ZoneInfo(master.timezone)
    start_at = datetime.fromisoformat(data["start_at"])
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            _render_confirm(client=client, service=service, start_at=start_at, comment=None, tz=tz),
            reply_markup=confirm_add_kb(),
        )


@router.callback_query(F.data == "master_add_save", MasterAdd.Confirming)
async def cb_confirm_save(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
    bot: Bot,
    app_bot: Bot | None = None,
) -> None:
    data = await state.get_data()
    client, service = await _load_client_service(session, master, data)
    if client is None or service is None:
        await state.clear()
        await callback.answer(strings.MANUAL_CANCELED, show_alert=True)
        return

    start_at = datetime.fromisoformat(data["start_at"])
    comment: str | None = data.get("comment")
    reminder_svc = ReminderService(session)
    svc = BookingService(session, reminder_service=reminder_svc)
    try:
        appt = await svc.create_manual(
            master=master, client=client, service=service, start_at=start_at, comment=comment
        )
    except SlotAlreadyTaken:
        await session.refresh(master)
        await session.refresh(service)
        await callback.answer(strings.MANUAL_SLOT_TAKEN, show_alert=True)
        await state.set_state(MasterAdd.PickingSlot)
        tz = ZoneInfo(master.timezone)
        picked = start_at.astimezone(tz).date()
        slots = await svc.get_free_slots(master, service, picked, now=now_utc())
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(
                strings.MANUAL_ASK_SLOT, reply_markup=slots_grid_with_custom(slots, tz=tz)
            )
        return

    await callback.answer(strings.MANUAL_SAVED)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.MANUAL_SAVED)
    await state.clear()

    if client.tg_id is not None:
        tz = ZoneInfo(master.timezone)
        local = appt.start_at.astimezone(tz)
        text = strings.CLIENT_NOTIFY_MANUAL.format(
            date=local.strftime("%d.%m.%Y"),
            time=local.strftime("%H:%M"),
            service=service.name,
        )
        from src.utils.client_notify import notify_client

        await notify_client(
            app_bot=app_bot,
            fallback_bot=bot,
            chat_id=client.tg_id,
            text=text,
            reply_markup=client_cancel_kb(appt.id),
        )
    log.info("manual_created", appointment_id=str(appt.id), master_tg=master.tg_id)


@router.callback_query(F.data == "master_add_cancel", MasterAdd.Confirming)
async def cb_confirm_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer(strings.MANUAL_CANCELED)
    await state.clear()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.MANUAL_CANCELED)


@router.message(Command("cancel"), MasterAdd.PickingClient)
@router.message(Command("cancel"), MasterAdd.SearchingClient)
@router.message(Command("cancel"), MasterAdd.NewClientName)
@router.message(Command("cancel"), MasterAdd.NewClientPhone)
@router.message(Command("cancel"), MasterAdd.PickingService)
@router.message(Command("cancel"), MasterAdd.PickingDate)
@router.message(Command("cancel"), MasterAdd.PickingSlot)
@router.message(Command("cancel"), MasterAdd.EnteringCustomTime)
@router.message(Command("cancel"), MasterAdd.EnteringComment)
@router.message(Command("cancel"), MasterAdd.Confirming)
async def cmd_cancel_any(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(strings.MANUAL_CANCELED)
