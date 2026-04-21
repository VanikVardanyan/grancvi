from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.mark_past import MarkPastCallback
from src.db.models import Master
from src.exceptions import InvalidState, NotFound
from src.handlers.master.today import _render_for, _safe_edit
from src.services.booking import BookingService
from src.strings import strings

router = Router(name="master_mark_past")

log: structlog.stdlib.BoundLogger = structlog.get_logger()


@router.callback_query(MarkPastCallback.filter())
async def cb_mark_past(
    callback: CallbackQuery,
    callback_data: MarkPastCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    svc = BookingService(session)
    try:
        if callback_data.action == "present":
            await svc.mark_completed(callback_data.appointment_id, master=master)
            ok_text: str = strings.MARK_PAST_OK_COMPLETED
        else:
            await svc.mark_no_show(callback_data.appointment_id, master=master)
            ok_text = strings.MARK_PAST_OK_NO_SHOW
    except NotFound:
        await callback.answer(strings.MARK_PAST_NOT_AVAILABLE, show_alert=True)
        return
    except InvalidState as exc:
        if "not ended" in str(exc):
            await callback.answer(strings.MARK_PAST_NOT_ENDED, show_alert=True)
        else:
            await callback.answer(strings.MARK_PAST_ALREADY_CLOSED, show_alert=True)
        return

    await callback.answer(ok_text)

    text, kb = await _render_for(session=session, master=master, offset_days=0)
    if isinstance(callback.message, Message):
        try:
            await _safe_edit(callback.message, text, kb)
        except TelegramBadRequest as exc:
            log.warning("mark_past edit failed", err=str(exc))
