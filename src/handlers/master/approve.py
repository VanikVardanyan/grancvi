from __future__ import annotations

from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.approval import ApprovalCallback
from src.db.models import Master
from src.exceptions import InvalidState, NotFound
from src.repositories.appointments import AppointmentRepository
from src.repositories.clients import ClientRepository
from src.repositories.services import ServiceRepository
from src.services.booking import BookingService
from src.services.reminders import ReminderService
from src.strings import strings
from src.utils.time import now_utc

router = Router(name="master_approve")
log: structlog.stdlib.BoundLogger = structlog.get_logger()

_ALERT_LIMIT = 190
_STATUS_LABELS = {
    "confirmed": "APPT_STATUS_CONFIRMED",
    "cancelled": "APPT_STATUS_CANCELLED",
    "rejected": "APPT_STATUS_REJECTED",
    "completed": "APPT_STATUS_COMPLETED",
    "no_show": "APPT_STATUS_NO_SHOW",
}


async def _notify_client(bot: Bot, client_tg_id: int | None, text: str) -> None:
    if client_tg_id is None:
        return
    try:
        await bot.send_message(chat_id=client_tg_id, text=text)
    except Exception as exc:
        log.warning("client_notify_failed", tg_id=client_tg_id, error=repr(exc))


@router.callback_query(ApprovalCallback.filter())
async def route_approval(
    callback: CallbackQuery,
    callback_data: ApprovalCallback,
    master: Master | None,
    session: AsyncSession,
    bot: Bot,
) -> None:
    if master is None:
        await callback.answer()
        return
    if callback_data.action == "confirm":
        await cb_confirm(
            callback, callback_data=callback_data, master=master, session=session, bot=bot
        )
    elif callback_data.action == "reject":
        await cb_reject(
            callback, callback_data=callback_data, master=master, session=session, bot=bot
        )
    elif callback_data.action == "history":
        await cb_history(
            callback, callback_data=callback_data, master=master, session=session, bot=bot
        )


async def cb_confirm(
    callback: CallbackQuery,
    *,
    callback_data: ApprovalCallback,
    master: Master,
    session: AsyncSession,
    bot: Bot,
) -> None:
    reminder_svc = ReminderService(session)
    svc = BookingService(session, reminder_service=reminder_svc)
    try:
        appt = await svc.confirm(callback_data.appointment_id, master_id=master.id)
    except (NotFound, InvalidState):
        await callback.answer(strings.APPT_ALREADY_PROCESSED, show_alert=True)
        return
    await session.flush()

    tz = ZoneInfo(master.timezone)
    local_now = now_utc().astimezone(tz)
    stamp = strings.APPT_CONFIRMED_STAMP.format(time=local_now.strftime("%H:%M"))

    if callback.message is not None and hasattr(callback.message, "edit_text"):
        original = getattr(callback.message, "text", "") or ""
        await callback.message.edit_text(original + stamp, reply_markup=None)
    await callback.answer()

    c_repo = ClientRepository(session)
    client = await c_repo.get(appt.client_id)
    if client is None:
        return
    s_repo = ServiceRepository(session)
    service = await s_repo.get(appt.service_id, master_id=master.id)
    if service is None:
        return
    local_appt = appt.start_at.astimezone(tz)
    text = strings.CLIENT_APPT_CONFIRMED.format(
        date=local_appt.strftime("%d.%m.%Y"),
        time=local_appt.strftime("%H:%M"),
    )
    await _notify_client(bot, client.tg_id, text)
    log.info("appointment_confirmed", id=str(appt.id))


async def cb_reject(
    callback: CallbackQuery,
    *,
    callback_data: ApprovalCallback,
    master: Master,
    session: AsyncSession,
    bot: Bot,
) -> None:
    svc = BookingService(session)
    try:
        appt = await svc.reject(callback_data.appointment_id, master_id=master.id)
    except (NotFound, InvalidState):
        await callback.answer(strings.APPT_ALREADY_PROCESSED, show_alert=True)
        return
    await session.flush()

    tz = ZoneInfo(master.timezone)
    local_now = now_utc().astimezone(tz)
    stamp = strings.APPT_REJECTED_STAMP.format(time=local_now.strftime("%H:%M"))

    if callback.message is not None and hasattr(callback.message, "edit_text"):
        original = getattr(callback.message, "text", "") or ""
        await callback.message.edit_text(original + stamp, reply_markup=None)
    await callback.answer()

    c_repo = ClientRepository(session)
    client = await c_repo.get(appt.client_id)
    if client is None:
        return
    local_appt = appt.start_at.astimezone(tz)
    text = strings.CLIENT_APPT_REJECTED.format(
        date=local_appt.strftime("%d.%m.%Y"),
        time=local_appt.strftime("%H:%M"),
    )
    await _notify_client(bot, client.tg_id, text)
    log.info("appointment_rejected", id=str(appt.id))


async def cb_history(
    callback: CallbackQuery,
    *,
    callback_data: ApprovalCallback,
    master: Master,
    session: AsyncSession,
    bot: Bot,
) -> None:
    a_repo = AppointmentRepository(session)
    appt = await a_repo.get(callback_data.appointment_id, master_id=master.id)
    if appt is None:
        await callback.answer(strings.APPT_ALREADY_PROCESSED, show_alert=True)
        return

    c_repo = ClientRepository(session)
    client = await c_repo.get(appt.client_id)
    if client is None:
        await callback.answer(strings.APPT_HISTORY_EMPTY, show_alert=True)
        return

    booking_svc = BookingService(session)
    history = await booking_svc.list_client_history(master, client.id, limit=10)
    if not history:
        await callback.answer(strings.APPT_HISTORY_EMPTY, show_alert=True)
        return

    tz = ZoneInfo(master.timezone)
    s_repo = ServiceRepository(session)
    lines = [strings.APPT_HISTORY_TITLE.format(name=client.name, limit=len(history))]
    for h in history:
        local = h.start_at.astimezone(tz)
        svc_row = await s_repo.get(h.service_id, master_id=master.id)
        svc_name = svc_row.name if svc_row else "—"
        status_key = _STATUS_LABELS.get(h.status, "APPT_STATUS_CONFIRMED")
        status_label = getattr(strings, status_key)
        lines.append(
            strings.APPT_HISTORY_LINE.format(
                date=local.strftime("%d.%m.%Y"),
                time=local.strftime("%H:%M"),
                service=svc_name,
                status=status_label,
            )
        )
    text = "\n".join(lines)

    if len(text) <= _ALERT_LIMIT:
        await callback.answer(text, show_alert=True)
        return

    await callback.answer()
    await bot.send_message(chat_id=master.tg_id, text=text)
