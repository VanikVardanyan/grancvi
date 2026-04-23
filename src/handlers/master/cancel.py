from __future__ import annotations

from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.master_cancel import MasterCancelCallback
from src.config import settings
from src.db.models import Client, Master, Service
from src.exceptions import InvalidState, NotFound
from src.handlers.master._common import safe_edit
from src.repositories.appointments import AppointmentRepository
from src.services.booking import BookingService
from src.services.reminders import ReminderService
from src.strings import strings
from src.utils.time import now_utc

router = Router(name="master_cancel")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


def _confirm_kb(appointment_id: str) -> InlineKeyboardMarkup:
    from uuid import UUID

    appt_uuid = UUID(appointment_id)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.MASTER_CANCEL_BTN_CONFIRM,
                    callback_data=MasterCancelCallback(
                        action="confirm", appointment_id=appt_uuid
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=strings.MASTER_CANCEL_BTN_ABORT,
                    callback_data=MasterCancelCallback(
                        action="abort", appointment_id=appt_uuid
                    ).pack(),
                ),
            ]
        ]
    )


@router.callback_query(MasterCancelCallback.filter())
async def cb_master_cancel(
    callback: CallbackQuery,
    callback_data: MasterCancelCallback,
    session: AsyncSession,
    master: Master | None,
    bot: Bot,
    app_bot: Bot | None = None,
) -> None:
    if master is None:
        await callback.answer()
        return

    if callback_data.action == "abort":
        await callback.answer()
        if isinstance(callback.message, Message):
            await _rerender_current_day(callback.message, session=session, master=master)
        return

    appt_repo = AppointmentRepository(session)
    appt = await appt_repo.get(callback_data.appointment_id)
    if appt is None or appt.master_id != master.id:
        await callback.answer(strings.MASTER_CANCEL_UNAVAILABLE, show_alert=True)
        return

    if callback_data.action == "ask":
        if appt.status not in ("pending", "confirmed") or appt.start_at <= now_utc():
            await callback.answer(strings.MASTER_CANCEL_UNAVAILABLE, show_alert=True)
            return
        client = await session.get(Client, appt.client_id)
        service = await session.get(Service, appt.service_id)
        if client is None or service is None:
            await callback.answer(strings.MASTER_CANCEL_UNAVAILABLE, show_alert=True)
            return
        tz = ZoneInfo(master.timezone)
        local = appt.start_at.astimezone(tz)
        text = strings.MASTER_CANCEL_ASK_FMT.format(
            client=client.name,
            service=service.name,
            date=local.strftime("%d.%m.%Y"),
            time=local.strftime("%H:%M"),
        )
        await callback.answer()
        if isinstance(callback.message, Message):
            await safe_edit(callback.message, text, _confirm_kb(str(appt.id)))
        return

    # action == "confirm"
    svc = BookingService(session)
    try:
        await svc.cancel(appt.id, cancelled_by="master")
    except (NotFound, InvalidState):
        await callback.answer(strings.MASTER_CANCEL_UNAVAILABLE, show_alert=True)
        return

    reminder_svc = ReminderService(session)
    await reminder_svc.suppress_for_appointment(appt.id)

    client = await session.get(Client, appt.client_id)
    service = await session.get(Service, appt.service_id)
    await session.commit()

    await callback.answer(strings.MASTER_CANCEL_DONE)

    if client is not None and client.tg_id is not None and service is not None:
        tz = ZoneInfo(master.timezone)
        local = appt.start_at.astimezone(tz)
        link = f"https://t.me/{settings.bot_username}?start=master_{master.slug}"
        text = strings.CLIENT_APPT_CANCELLED_BY_MASTER.format(
            date=local.strftime("%d.%m.%Y"),
            time=local.strftime("%H:%M"),
            service=service.name,
            link=link,
        )
        from src.utils.client_notify import notify_client

        await notify_client(app_bot=app_bot, master_bot=bot, chat_id=client.tg_id, text=text)

    log.info("master_cancelled_appointment", appointment_id=str(appt.id))

    if isinstance(callback.message, Message):
        await _rerender_current_day(callback.message, session=session, master=master)


async def _rerender_current_day(
    message: Message,
    *,
    session: AsyncSession,
    master: Master,
) -> None:
    """Redraw the day view this callback came from by re-rendering 'today'."""
    from src.handlers.master.today import _render_for

    text, kb = await _render_for(session=session, master=master, offset_days=0)
    await safe_edit(message, text, kb)
