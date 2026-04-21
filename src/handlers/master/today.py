from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.schedule import DayNavCallback
from src.db.models import Master
from src.fsm.master_add import MasterAdd
from src.keyboards.master_add import recent_clients_kb
from src.repositories.appointments import AppointmentRepository
from src.repositories.clients import ClientRepository
from src.repositories.services import ServiceRepository
from src.strings import strings
from src.utils.schedule_format import render_day_schedule
from src.utils.time import now_utc

router = Router(name="master_today")


async def _safe_edit(message: Message, text: str, reply_markup: InlineKeyboardMarkup) -> None:
    """edit_text that swallows 'message is not modified' errors."""
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc):
            raise


def _day_nav(kind: Literal["today", "tomorrow"]) -> list[list[InlineKeyboardButton]]:
    if kind == "today":
        primary = InlineKeyboardButton(
            text=strings.DAY_NAV_TOMORROW,
            callback_data=DayNavCallback(action="tomorrow").pack(),
        )
    else:
        primary = InlineKeyboardButton(
            text=strings.DAY_NAV_TODAY,
            callback_data=DayNavCallback(action="today").pack(),
        )
    return [
        [
            primary,
            InlineKeyboardButton(
                text=strings.DAY_NAV_WEEK,
                callback_data=DayNavCallback(action="week").pack(),
            ),
            InlineKeyboardButton(
                text=strings.DAY_NAV_ADD,
                callback_data=DayNavCallback(action="add").pack(),
            ),
        ]
    ]


async def _render_for(
    *,
    session: AsyncSession,
    master: Master,
    offset_days: int,
) -> tuple[str, InlineKeyboardMarkup]:
    tz = ZoneInfo(master.timezone)
    today_local = now_utc().astimezone(tz).date()
    d = today_local + timedelta(days=offset_days)

    day_start_utc = datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(UTC)
    day_end_utc = day_start_utc + timedelta(days=1)
    repo = AppointmentRepository(session)
    appts = await repo.list_for_master_range(
        master.id,
        start_utc=day_start_utc,
        end_utc=day_end_utc,
        statuses=("pending", "confirmed", "completed", "no_show"),
    )

    client_ids = {a.client_id for a in appts}
    service_ids = {a.service_id for a in appts}
    client_names = await ClientRepository(session).get_names_by_ids(client_ids)
    service_names = await ServiceRepository(session).get_names_by_ids(service_ids)

    kind: Literal["today", "tomorrow"] = "today" if offset_days == 0 else "tomorrow"
    return render_day_schedule(
        d=d,
        appts=appts,
        client_names=client_names,
        service_names=service_names,
        work_hours=master.work_hours,
        breaks=master.breaks,
        tz=tz,
        slot_step_min=master.slot_step_min,
        now=now_utc(),
        day_nav=_day_nav(kind),
    )


@router.message(Command("today"))
async def cmd_today(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await state.clear()
    text, kb = await _render_for(session=session, master=master, offset_days=0)
    await message.answer(text, reply_markup=kb)


@router.message(Command("tomorrow"))
async def cmd_tomorrow(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await state.clear()
    text, kb = await _render_for(session=session, master=master, offset_days=1)
    await message.answer(text, reply_markup=kb)


@router.callback_query(DayNavCallback.filter())
async def cb_day_nav(
    callback: CallbackQuery,
    callback_data: DayNavCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    action = callback_data.action
    if action == "today":
        text, kb = await _render_for(session=session, master=master, offset_days=0)
        if isinstance(callback.message, Message):
            await _safe_edit(callback.message, text, kb)
        return
    if action == "tomorrow":
        text, kb = await _render_for(session=session, master=master, offset_days=1)
        if isinstance(callback.message, Message):
            await _safe_edit(callback.message, text, kb)
        return
    if action == "week":
        from src.handlers.master.week import render_week  # local import avoids cycle

        text, kb = await render_week(session=session, master=master)
        if isinstance(callback.message, Message):
            await _safe_edit(callback.message, text, kb)
        return
    # Epic 6: re-enabled in Task 12
    # if action == "calendar":
    #     from src.handlers.master.calendar import render_calendar
    #
    #     text, kb = await render_calendar(session=session, master=master, month=None)
    #     if callback.message is not None and hasattr(callback.message, "edit_text"):
    #         await callback.message.edit_text(text, reply_markup=kb)
    #     return
    if action == "add":
        await state.clear()
        await state.set_state(MasterAdd.PickingClient)
        repo = ClientRepository(session)
        clients = await repo.list_recent_by_master(master.id)
        text_prompt = strings.MANUAL_PICK_CLIENT if clients else strings.MANUAL_NO_RECENT
        if callback.message is not None and hasattr(callback.message, "answer"):
            await callback.message.answer(text_prompt, reply_markup=recent_clients_kb(clients))
        return
