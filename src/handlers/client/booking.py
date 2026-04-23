from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.calendar import CalendarCallback
from src.callback_data.client_services import ClientServicePick
from src.callback_data.slots import SlotCallback
from src.db.models import Master, Service
from src.exceptions import SlotAlreadyTaken
from src.fsm.client_booking import ClientBooking
from src.keyboards.calendar import calendar_keyboard
from src.keyboards.slots import approval_kb, confirm_kb, slots_grid
from src.repositories.clients import ClientRepository
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.strings import strings
from src.utils.phone import normalize as normalize_phone
from src.utils.time import now_utc

router = Router(name="client_booking")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


async def _resolve_master_id(session: AsyncSession, data: dict[str, Any]) -> UUID | None:
    raw = data.get("master_id")
    if raw:
        return UUID(raw)
    return None


async def _load_master_service(
    session: AsyncSession, master_id: UUID, service_id: UUID
) -> tuple[Master | None, Service | None]:
    m_repo = MasterRepository(session)
    s_repo = ServiceRepository(session)
    master = await m_repo.by_id(master_id)
    if master is None or master.blocked_at is not None or not master.is_public:
        return None, None
    service = await s_repo.get(service_id, master_id=master_id)
    return master, service


async def _render_calendar(
    *,
    target: Any,  # Message or CallbackQuery.message
    master: Master,
    service: Service,
    state: FSMContext,
    session: AsyncSession,
    month: date | None = None,
) -> None:
    now = now_utc()
    tz = ZoneInfo(master.timezone)
    today = now.astimezone(tz).date()
    the_month = month or today.replace(day=1)

    svc = BookingService(session)
    loads = await svc.get_month_load(master=master, service=service, month=the_month, now=now)

    await target.answer(
        strings.CLIENT_CHOOSE_DATE,
        reply_markup=calendar_keyboard(month=the_month, loads=loads, today=today),
    )
    await state.set_state(ClientBooking.ChoosingDate)


@router.callback_query(ClientServicePick.filter(), ClientBooking.ChoosingService)
async def handle_service_pick(
    callback: CallbackQuery,
    callback_data: ClientServicePick,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    master_id = await _resolve_master_id(session, data)
    if master_id is None:
        await callback.answer(strings.CLIENT_START_NO_MASTER, show_alert=True)
        await state.clear()
        return
    master, service = await _load_master_service(session, master_id, callback_data.service_id)
    if master is None or service is None:
        await callback.answer(strings.CLIENT_NO_SERVICES, show_alert=True)
        await state.clear()
        return

    await state.update_data(master_id=str(master.id), service_id=str(service.id))
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await _render_calendar(
            target=callback.message,
            master=master,
            service=service,
            state=state,
            session=session,
        )


@router.callback_query(CalendarCallback.filter(), ClientBooking.ChoosingDate)
async def handle_date_pick(
    callback: CallbackQuery,
    callback_data: CalendarCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback_data.action == "noop":
        await callback.answer()
        return

    data = await state.get_data()
    master_id = await _resolve_master_id(session, data)
    service_raw = data.get("service_id")
    if master_id is None or not service_raw:
        await callback.answer(strings.CLIENT_NO_SERVICES, show_alert=True)
        await state.clear()
        return
    master, service = await _load_master_service(session, master_id, UUID(service_raw))
    if master is None or service is None:
        await callback.answer(strings.CLIENT_NO_SERVICES, show_alert=True)
        await state.clear()
        return

    if callback_data.action == "nav":
        await callback.answer()
        if callback.message is not None and hasattr(callback.message, "answer"):
            await _render_calendar(
                target=callback.message,
                master=master,
                service=service,
                state=state,
                session=session,
                month=date(callback_data.year, callback_data.month, 1),
            )
        return

    # action == "pick"
    picked = date(callback_data.year, callback_data.month, callback_data.day)
    tz = ZoneInfo(master.timezone)
    svc = BookingService(session)
    slots = await svc.get_free_slots(master, service, picked, now=now_utc())

    await callback.answer()
    if callback.message is None or not hasattr(callback.message, "answer"):
        return

    if not slots:
        await callback.message.answer(strings.CLIENT_NO_SLOTS)
        await _render_calendar(
            target=callback.message,
            master=master,
            service=service,
            state=state,
            session=session,
            month=picked.replace(day=1),
        )
        return

    await state.update_data(date=picked.isoformat())
    await state.set_state(ClientBooking.ChoosingTime)
    await callback.message.answer(
        strings.CLIENT_CHOOSE_TIME.format(date=picked.strftime("%d.%m.%Y")),
        reply_markup=slots_grid(slots, tz=tz),
    )


@router.callback_query(SlotCallback.filter(), ClientBooking.ChoosingTime)
async def handle_time_pick(
    callback: CallbackQuery,
    callback_data: SlotCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    master_id = UUID(data["master_id"])
    service_id = UUID(data["service_id"])
    picked_day = date.fromisoformat(data["date"])

    master, service = await _load_master_service(session, master_id, service_id)
    if master is None or service is None:
        await callback.answer(strings.CLIENT_NO_SERVICES, show_alert=True)
        await state.clear()
        return

    tz = ZoneInfo(master.timezone)
    local_start = datetime(
        picked_day.year,
        picked_day.month,
        picked_day.day,
        callback_data.hour,
        callback_data.minute,
        tzinfo=tz,
    )
    start_at_utc = local_start.astimezone(ZoneInfo("UTC"))

    await state.update_data(start_at=start_at_utc.isoformat())
    await state.set_state(ClientBooking.EnteringName)
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.CLIENT_ASK_NAME)


@router.message(ClientBooking.EnteringName)
async def handle_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not (1 <= len(name) <= 60):
        await message.answer(strings.CLIENT_BAD_NAME)
        return
    await state.update_data(name=name)
    await state.set_state(ClientBooking.EnteringPhone)
    await message.answer(strings.CLIENT_ASK_PHONE)


@router.message(ClientBooking.EnteringPhone)
async def handle_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    raw = (message.text or "").strip()
    normalized = normalize_phone(raw)
    if normalized is None:
        await message.answer(strings.CLIENT_BAD_PHONE)
        return

    await state.update_data(phone=normalized)
    await state.set_state(ClientBooking.Confirming)

    data = await state.get_data()
    master_id = UUID(data["master_id"])
    service_id = UUID(data["service_id"])
    master, service = await _load_master_service(session, master_id, service_id)
    if master is None or service is None:
        await state.clear()
        await message.answer(strings.CLIENT_NO_SERVICES)
        return

    tz = ZoneInfo(master.timezone)
    start_at_utc = datetime.fromisoformat(data["start_at"])
    local = start_at_utc.astimezone(tz)
    summary = strings.CLIENT_CONFIRM_TITLE.format(
        service=service.name,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        name=data["name"],
        phone=normalized,
    )
    await message.answer(summary, reply_markup=confirm_kb())


@router.callback_query(F.data == "client_cancel")
async def handle_cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.CLIENT_CANCELLED)


@router.callback_query(F.data == "client_back", ClientBooking.ChoosingTime)
async def handle_back_from_time(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    master_id = UUID(data["master_id"])
    service_id = UUID(data["service_id"])
    master, service = await _load_master_service(session, master_id, service_id)
    if master is None or service is None:
        await state.clear()
        await callback.answer()
        return
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await _render_calendar(
            target=callback.message,
            master=master,
            service=service,
            state=state,
            session=session,
        )


@router.callback_query(F.data == "client_confirm", ClientBooking.Confirming)
async def handle_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    data = await state.get_data()
    master_id = UUID(data["master_id"])
    service_id = UUID(data["service_id"])
    master, service = await _load_master_service(session, master_id, service_id)
    if master is None or service is None:
        await state.clear()
        await callback.answer(strings.CLIENT_NO_SERVICES, show_alert=True)
        return

    c_repo = ClientRepository(session)
    tg_id = callback.from_user.id if callback.from_user else None
    client_row = await c_repo.upsert_by_phone(
        master_id=master.id,
        phone=data["phone"],
        name=data["name"],
        tg_id=tg_id,
    )
    await session.commit()

    start_at_utc = datetime.fromisoformat(data["start_at"])
    svc = BookingService(session)
    try:
        appt = await svc.create_pending(
            master=master,
            client=client_row,
            service=service,
            start_at=start_at_utc,
        )
    except SlotAlreadyTaken:
        # After rollback all ORM objects are expired; refresh before re-querying.
        await session.refresh(master)
        await session.refresh(service)
        await callback.answer(strings.CLIENT_SLOT_TAKEN, show_alert=True)
        await state.set_state(ClientBooking.ChoosingTime)
        tz = ZoneInfo(master.timezone)
        slots = await svc.get_free_slots(
            master,
            service,
            start_at_utc.astimezone(tz).date(),
            now=now_utc(),
        )
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(strings.CLIENT_SLOT_TAKEN)
            if slots:
                await callback.message.answer(
                    strings.CLIENT_CHOOSE_TIME.format(
                        date=start_at_utc.astimezone(tz).strftime("%d.%m.%Y"),
                    ),
                    reply_markup=slots_grid(slots, tz=tz),
                )
            else:
                await callback.message.answer(strings.CLIENT_NO_SLOTS)
        return

    await state.clear()
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.CLIENT_SENT)

    tz = ZoneInfo(master.timezone)
    local = appt.start_at.astimezone(tz)
    weekday_ru = strings.WEEKDAY_SHORT[local.weekday()]
    text = strings.APPT_NOTIFY_MASTER.format(
        name=client_row.name,
        phone=client_row.phone or "—",
        service=service.name,
        duration=service.duration_min,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        weekday=weekday_ru,
    )
    await bot.send_message(
        chat_id=master.tg_id,
        text=text,
        reply_markup=approval_kb(appt.id),
    )
    log.info("pending_created", appointment_id=str(appt.id), master_tg=master.tg_id)
