"""Callback handlers for in-chat Approve / Reject buttons.

Lives on @grancviWebBot so masters can confirm / reject a pending
request from the notification itself — one tap, no TMA hop.
Session is created per callback (no middleware on this bot), which is
fine for the low frequency of approvals.
"""

from __future__ import annotations

from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.approval import ApprovalCallback
from src.db.base import SessionMaker
from src.db.models import Appointment, Client, Master, Service
from src.exceptions import InvalidState, NotFound
from src.repositories.appointments import AppointmentRepository
from src.services.booking import BookingService
from src.services.reminders import ReminderService
from src.strings import strings

router = Router(name="app_bot_approval")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


async def _notify_client(
    bot: object,
    appt: Appointment,
    session: AsyncSession,
    template: str,
) -> None:
    """Push status update to the client's TG when they have one."""
    client = await session.get(Client, appt.client_id)
    if client is None or client.tg_id is None:
        return
    master = await session.get(Master, appt.master_id)
    service = await session.get(Service, appt.service_id)
    if master is None or service is None:
        return
    tz = ZoneInfo(master.timezone)
    local = appt.start_at.astimezone(tz)
    text = template.format(
        master=master.name,
        service=service.name,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        link="",
    )
    try:
        await bot.send_message(chat_id=client.tg_id, text=text)  # type: ignore[attr-defined]
    except Exception as exc:
        log.warning("approval_client_notify_failed", err=repr(exc))


async def _ensure_master_owns(
    callback: CallbackQuery, appt_id: UUID, session: AsyncSession
) -> Appointment | None:
    """Confirm the caller is the master on this appointment; alert otherwise."""
    if callback.from_user is None:
        await callback.answer("No user", show_alert=True)
        return None
    appt = await AppointmentRepository(session).get(appt_id)
    if appt is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return None
    master = await session.get(Master, appt.master_id)
    if master is None or master.tg_id != callback.from_user.id:
        await callback.answer("Недоступно", show_alert=True)
        return None
    return appt


@router.callback_query(ApprovalCallback.filter(F.action == "confirm"))
async def on_confirm(callback: CallbackQuery, callback_data: ApprovalCallback) -> None:
    async with SessionMaker() as session:
        appt = await _ensure_master_owns(callback, callback_data.appointment_id, session)
        if appt is None:
            return
        reminder_svc = ReminderService(session)
        svc = BookingService(session, reminder_service=reminder_svc)
        try:
            appt = await svc.confirm(appt.id, master_id=appt.master_id)
        except (NotFound, InvalidState):
            await callback.answer("Уже обработано", show_alert=True)
            return
        await session.commit()
        await session.refresh(appt)
        await _notify_client(callback.bot, appt, session, strings.CLIENT_APPT_CONFIRMED)

    await callback.answer("Подтверждено ✅")
    await _clear_buttons(callback)


@router.callback_query(ApprovalCallback.filter(F.action == "reject"))
async def on_reject(callback: CallbackQuery, callback_data: ApprovalCallback) -> None:
    async with SessionMaker() as session:
        appt = await _ensure_master_owns(callback, callback_data.appointment_id, session)
        if appt is None:
            return
        svc = BookingService(session)
        try:
            appt = await svc.reject(appt.id, master_id=appt.master_id)
        except (NotFound, InvalidState):
            await callback.answer("Уже обработано", show_alert=True)
            return
        await session.commit()
        await session.refresh(appt)
        await _notify_client(callback.bot, appt, session, strings.CLIENT_APPT_REJECTED)

    await callback.answer("Отклонено")
    await _clear_buttons(callback)


async def _clear_buttons(callback: CallbackQuery) -> None:
    """Remove the inline keyboard from the notification so the master
    can't double-tap. Swallows errors — an ineditable / old message
    isn't worth alerting on.
    """
    import contextlib

    msg = callback.message
    if msg is None:
        return
    edit = getattr(msg, "edit_reply_markup", None)
    if edit is None:
        return
    with contextlib.suppress(Exception):
        await edit(reply_markup=None)
