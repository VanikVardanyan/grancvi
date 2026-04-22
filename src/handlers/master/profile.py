from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.profile import ProfileFieldCallback
from src.db.models import Master
from src.exceptions import InvalidSlug, ReservedSlug, SlugTaken
from src.fsm.profile import ProfileEdit
from src.repositories.masters import MasterRepository
from src.services.slug import SlugService
from src.strings import strings

router = Router(name="master_profile")


def profile_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=strings.PROFILE_BTN_NAME,
                callback_data=ProfileFieldCallback(field="name").pack(),
            )],
            [InlineKeyboardButton(
                text=strings.PROFILE_BTN_SPECIALTY,
                callback_data=ProfileFieldCallback(field="specialty").pack(),
            )],
            [InlineKeyboardButton(
                text=strings.PROFILE_BTN_SLUG,
                callback_data=ProfileFieldCallback(field="slug").pack(),
            )],
        ]
    )


async def open_profile_menu(
    *, message: Message, state: FSMContext, master: Master
) -> None:
    await state.set_state(ProfileEdit.menu)
    await message.answer(strings.PROFILE_MENU_TITLE, reply_markup=profile_menu_kb())


@router.callback_query(ProfileFieldCallback.filter(F.field == "name"))
async def pick_name(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileEdit.waiting_name)
    if cb.message is not None:
        await cb.message.answer(strings.PROFILE_ASK_NEW_NAME)
    await cb.answer()


@router.callback_query(ProfileFieldCallback.filter(F.field == "specialty"))
async def pick_specialty(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileEdit.waiting_specialty)
    if cb.message is not None:
        await cb.message.answer(strings.PROFILE_ASK_NEW_SPECIALTY)
    await cb.answer()


@router.callback_query(ProfileFieldCallback.filter(F.field == "slug"))
async def pick_slug(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileEdit.waiting_slug)
    if cb.message is not None:
        await cb.message.answer(strings.PROFILE_ASK_NEW_SLUG)
    await cb.answer()


@router.message(ProfileEdit.waiting_name)
async def cmd_profile_save_name(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(strings.PROFILE_ASK_NEW_NAME)
        return
    await MasterRepository(session).update_name(master.id, name)
    await session.commit()
    await state.clear()
    await message.answer(strings.PROFILE_UPDATED)


@router.message(ProfileEdit.waiting_specialty)
async def cmd_profile_save_specialty(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    specialty = (message.text or "").strip()
    if not specialty:
        await message.answer(strings.PROFILE_ASK_NEW_SPECIALTY)
        return
    await MasterRepository(session).update_specialty(master.id, specialty)
    await session.commit()
    await state.clear()
    await message.answer(strings.PROFILE_UPDATED)


@router.message(ProfileEdit.waiting_slug)
async def cmd_profile_save_slug(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    slug = (message.text or "").strip().lower()
    try:
        SlugService.validate(slug)
    except ReservedSlug:
        await message.answer(strings.REGISTER_SLUG_RESERVED)
        return
    except InvalidSlug:
        await message.answer(strings.REGISTER_SLUG_INVALID)
        return

    repo = MasterRepository(session)
    existing = await repo.by_slug(slug)
    if existing is not None and existing.id != master.id:
        await message.answer(strings.REGISTER_SLUG_TAKEN)
        return

    try:
        await repo.update_slug(master.id, slug)
        await session.commit()
    except SlugTaken:
        await message.answer(strings.REGISTER_SLUG_TAKEN)
        return

    await state.clear()
    await message.answer(strings.PROFILE_UPDATED)
