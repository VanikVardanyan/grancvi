from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.calendar import CalendarCallback
from src.callback_data.client_services import ClientServicePick
from src.db.models import Master, Service
from src.fsm.client_booking import ClientBooking
from src.keyboards.calendar import calendar_keyboard
from src.keyboards.slots import slots_grid
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.strings import strings
from src.utils.time import now_utc

router = Router(name="client_booking")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


async def _resolve_master_id(session: AsyncSession, data: dict[str, Any]) -> UUID | None:
    raw = data.get("master_id")
    if raw:
        return UUID(raw)
    m = await MasterRepository(session).get_singleton()
    return m.id if m else None


async def _load_master_service(
    session: AsyncSession, master_id: UUID, service_id: UUID
) -> tuple[Master | None, Service | None]:
    m_repo = MasterRepository(session)
    s_repo = ServiceRepository(session)
    master = await m_repo.get_singleton()
    if master is None or master.id != master_id:
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
            target=callback.message, master=master, service=service,
            state=state, session=session,
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
                target=callback.message, master=master, service=service,
                state=state, session=session,
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
            target=callback.message, master=master, service=service,
            state=state, session=session,
            month=picked.replace(day=1),
        )
        return

    await state.update_data(date=picked.isoformat())
    await state.set_state(ClientBooking.ChoosingTime)
    await callback.message.answer(
        strings.CLIENT_CHOOSE_TIME.format(date=picked.strftime("%d.%m.%Y")),
        reply_markup=slots_grid(slots, tz=tz),
    )
