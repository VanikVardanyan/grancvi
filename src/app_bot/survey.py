from __future__ import annotations

import structlog
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.admin import SurveyRatingCallback, SurveySkipCallback
from src.config import settings
from src.fsm.survey import SurveyAdmin, SurveyFeedback
from src.repositories.masters import MasterRepository
from src.strings import strings

router = Router(name="app_bot_survey")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


def _rating_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=str(r),
                    callback_data=SurveyRatingCallback(rating=r).pack(),
                )
                for r in range(1, 6)
            ]
        ]
    )


def _skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.ADMIN_SURVEY_SKIP_BTN,
                    callback_data=SurveySkipCallback().pack(),
                )
            ]
        ]
    )


@router.message(Command("survey"))
async def handle_survey_cmd(
    message: Message,
    state: FSMContext,
) -> None:
    tg_id = message.from_user.id if message.from_user else 0
    if tg_id not in settings.admin_tg_ids:
        return
    await state.set_state(SurveyAdmin.waiting_text)
    await message.answer(strings.ADMIN_SURVEY_ASK_TEXT)


@router.message(SurveyAdmin.waiting_text)
async def handle_survey_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
) -> None:
    text = message.text or ""
    if not text:
        await message.answer(strings.ADMIN_SURVEY_ASK_TEXT)
        return
    await state.clear()
    repo = MasterRepository(session)
    masters = await repo.list_all()
    active = [m for m in masters if m.blocked_at is None and m.tg_id is not None]
    if not active:
        await message.answer(strings.ADMIN_SURVEY_NO_MASTERS)
        return
    await message.answer(strings.ADMIN_SURVEY_SENDING_FMT.format(n=len(active)))
    sent = 0
    for master in active:
        try:
            await bot.send_message(
                master.tg_id,
                text,
                reply_markup=_rating_kb(),
            )
            sent += 1
        except Exception as exc:
            log.warning("survey_send_failed", master_tg_id=master.tg_id, err=repr(exc))
    await message.answer(strings.ADMIN_SURVEY_SENT_FMT.format(n=sent))


@router.callback_query(SurveyRatingCallback.filter())
async def cb_survey_rating(
    callback: CallbackQuery,
    callback_data: SurveyRatingCallback,
    state: FSMContext,
) -> None:
    await state.set_state(SurveyFeedback.waiting_comment)
    await state.update_data(rating=callback_data.rating)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            strings.ADMIN_SURVEY_ASK_COMMENT_FMT.format(rating=callback_data.rating),
            reply_markup=_skip_kb(),
        )


@router.callback_query(SurveySkipCallback.filter())
async def cb_survey_skip(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    data = await state.get_data()
    rating = data.get("rating", "?")
    name = callback.from_user.full_name if callback.from_user else "?"
    tg_id = callback.from_user.id if callback.from_user else 0
    await state.clear()
    await callback.answer()
    await _notify_admin(bot, name=name, tg_id=tg_id, rating=rating, comment=None)
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(strings.ADMIN_SURVEY_DONE)


@router.message(SurveyFeedback.waiting_comment)
async def handle_survey_comment(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    data = await state.get_data()
    rating = data.get("rating", "?")
    name = message.from_user.full_name if message.from_user else "?"
    tg_id = message.from_user.id if message.from_user else 0
    comment = message.text or ""
    await state.clear()
    await _notify_admin(bot, name=name, tg_id=tg_id, rating=rating, comment=comment)
    await message.answer(strings.ADMIN_SURVEY_DONE)


async def _notify_admin(
    bot: Bot, *, name: str, tg_id: int, rating: int | str, comment: str | None
) -> None:
    if not settings.admin_tg_ids:
        return
    text = strings.ADMIN_SURVEY_REPORT_FMT.format(
        name=name,
        tg_id=tg_id,
        rating=rating,
        comment=comment if comment else strings.ADMIN_SURVEY_NO_COMMENT,
    )
    for admin_id in settings.admin_tg_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:
            log.warning("survey_notify_admin_failed", admin_id=admin_id, err=repr(exc))
