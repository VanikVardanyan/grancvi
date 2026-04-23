from __future__ import annotations

from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.approval import ApprovalCallback
from src.config import settings
from src.exceptions import InvalidState, NotFound
from src.services.booking import BookingService
from src.services.reminders import ReminderService
from src.strings import strings

router = Router(name="client_cancel")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


@router.callback_query(ApprovalCallback.filter(F.action == "cancel"))
async def handle_cancel(
    callback: CallbackQuery,
    callback_data: ApprovalCallback,
    session: AsyncSession,
    bot: Bot,
) -> None:
    tg_id = callback.from_user.id if callback.from_user else 0
    svc = BookingService(session)
    try:
        appt, client, master, service = await svc.cancel_by_client(
            callback_data.appointment_id, tg_id=tg_id
        )
    except (NotFound, InvalidState):
        await callback.answer(strings.CLIENT_CANCEL_UNAVAILABLE, show_alert=True)
        return
    reminder_svc = ReminderService(session)
    await reminder_svc.suppress_for_appointment(appt.id)
    await session.commit()

    await callback.answer(strings.CLIENT_CANCEL_DONE)
    if callback.message is not None and hasattr(callback.message, "edit_reply_markup"):
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            log.warning("cancel_kb_strip_failed", appointment_id=str(appt.id))

    if callback.message is not None and hasattr(callback.message, "answer"):
        link = f"https://t.me/{settings.bot_username}?start=master_{master.slug}"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=strings.CLIENT_BOOK_AGAIN_BTN, url=link)]]
        )
        await callback.message.answer(strings.CLIENT_CANCEL_DONE, reply_markup=kb)

    tz = ZoneInfo(master.timezone)
    local = appt.start_at.astimezone(tz)
    text = strings.MASTER_NOTIFY_CLIENT_CANCELED.format(
        name=client.name,
        date=local.strftime("%d.%m.%Y"),
        time=local.strftime("%H:%M"),
        service=service.name,
    )
    try:
        await bot.send_message(chat_id=master.tg_id, text=text)
    except Exception:
        log.warning("master_notify_failed", master_tg=master.tg_id)
    log.info("client_cancelled", appointment_id=str(appt.id), client_tg=tg_id)
