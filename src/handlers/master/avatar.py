from __future__ import annotations

import io

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.profile import AvatarActionCallback, ProfileFieldCallback
from src.config import settings
from src.db.models import Master
from src.exceptions import BadImage
from src.fsm.master_register import MasterRegister
from src.fsm.profile import ProfileEdit
from src.keyboards.common import main_menu
from src.repositories.masters import MasterRepository
from src.services.avatars import AvatarService
from src.strings import strings
from src.utils.time import now_utc

router = Router(name="master_avatar")


_MAX_AVATAR_BYTES = 10 * 1024 * 1024


def _avatar_service() -> AvatarService:
    return AvatarService(directory=settings.avatars_dir)


def _onboarding_skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.REGISTER_AVATAR_SKIP_BTN,
                    callback_data=AvatarActionCallback(action="skip").pack(),
                )
            ]
        ]
    )


def _profile_avatar_present_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_AVATAR_REPLACE_BTN,
                    callback_data=AvatarActionCallback(action="replace").pack(),
                ),
                InlineKeyboardButton(
                    text=strings.PROFILE_AVATAR_DELETE_BTN,
                    callback_data=AvatarActionCallback(action="delete").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_AVATAR_BACK_BTN,
                    callback_data=AvatarActionCallback(action="back").pack(),
                )
            ],
        ]
    )


def _profile_avatar_absent_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_AVATAR_SEND_BTN,
                    callback_data=AvatarActionCallback(action="replace").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.PROFILE_AVATAR_BACK_BTN,
                    callback_data=AvatarActionCallback(action="back").pack(),
                )
            ],
        ]
    )


async def _download_photo_bytes(message: Message) -> bytes | None:
    """Pull the largest photo or an image document. Returns None if oversize."""
    if message.bot is None:
        return None
    if message.photo:
        photo = message.photo[-1]
        if photo.file_size and photo.file_size > _MAX_AVATAR_BYTES:
            return None
        buf = io.BytesIO()
        await message.bot.download(photo, destination=buf)
        return buf.getvalue()
    if message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
        doc = message.document
        if doc.file_size and doc.file_size > _MAX_AVATAR_BYTES:
            return None
        buf = io.BytesIO()
        await message.bot.download(doc, destination=buf)
        return buf.getvalue()
    return None


async def _persist_avatar(
    *,
    raw: bytes,
    master: Master,
    session: AsyncSession,
) -> None:
    _avatar_service().save(master.id, raw)
    await MasterRepository(session).set_avatar_uploaded_at(master.id, now_utc())
    await session.commit()


@router.message(MasterRegister.waiting_avatar, F.photo | F.document)
async def onboarding_avatar_received(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    raw = await _download_photo_bytes(message)
    if raw is None:
        if message.document and not (message.document.mime_type or "").startswith("image/"):
            await message.answer(strings.AVATAR_NEED_PHOTO)
            return
        await message.answer(strings.AVATAR_TOO_LARGE)
        return
    try:
        await _persist_avatar(raw=raw, master=master, session=session)
    except BadImage:
        await message.answer(strings.AVATAR_BAD_IMAGE)
        return
    await state.clear()
    await message.answer(strings.REGISTER_DONE, reply_markup=main_menu())


@router.message(MasterRegister.waiting_avatar)
async def onboarding_avatar_other(message: Message) -> None:
    await message.answer(strings.AVATAR_NEED_PHOTO)


@router.callback_query(
    MasterRegister.waiting_avatar,
    AvatarActionCallback.filter(F.action == "skip"),
)
async def onboarding_avatar_skip(cb: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if cb.message is not None:
        await cb.message.answer(strings.REGISTER_DONE, reply_markup=main_menu())
    await cb.answer()


@router.callback_query(ProfileFieldCallback.filter(F.field == "avatar"))
async def profile_avatar_open(
    cb: CallbackQuery,
    state: FSMContext,
    master: Master,
) -> None:
    await state.set_state(ProfileEdit.menu)
    if cb.message is None:
        await cb.answer()
        return
    if master.avatar_uploaded_at is not None:
        path = _avatar_service().path_for(master.id)
        if path.exists():
            await cb.message.answer_photo(
                photo=FSInputFile(str(path)),
                caption=strings.PROFILE_AVATAR_PRESENT,
                reply_markup=_profile_avatar_present_kb(),
            )
            await cb.answer()
            return
    await cb.message.answer(
        strings.PROFILE_AVATAR_NONE,
        reply_markup=_profile_avatar_absent_kb(),
    )
    await cb.answer()


@router.callback_query(AvatarActionCallback.filter(F.action == "replace"))
async def profile_avatar_replace(cb: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileEdit.waiting_avatar)
    if cb.message is not None:
        await cb.message.answer(strings.REGISTER_ASK_AVATAR)
    await cb.answer()


@router.callback_query(AvatarActionCallback.filter(F.action == "delete"))
async def profile_avatar_delete(
    cb: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    _avatar_service().delete(master.id)
    await MasterRepository(session).set_avatar_uploaded_at(master.id, None)
    await session.commit()
    await state.clear()
    if cb.message is not None:
        await cb.message.answer(strings.AVATAR_DELETED)
    await cb.answer()


@router.callback_query(AvatarActionCallback.filter(F.action == "back"))
async def profile_avatar_back(cb: CallbackQuery, state: FSMContext) -> None:
    from src.handlers.master.profile import profile_menu_kb

    await state.set_state(ProfileEdit.menu)
    if cb.message is not None:
        await cb.message.answer(strings.PROFILE_MENU_TITLE, reply_markup=profile_menu_kb())
    await cb.answer()


@router.message(ProfileEdit.waiting_avatar, F.photo | F.document)
async def profile_avatar_received(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    raw = await _download_photo_bytes(message)
    if raw is None:
        if message.document and not (message.document.mime_type or "").startswith("image/"):
            await message.answer(strings.AVATAR_NEED_PHOTO)
            return
        await message.answer(strings.AVATAR_TOO_LARGE)
        return
    try:
        await _persist_avatar(raw=raw, master=master, session=session)
    except BadImage:
        await message.answer(strings.AVATAR_BAD_IMAGE)
        return
    await state.clear()
    await message.answer(strings.PROFILE_UPDATED)


@router.message(ProfileEdit.waiting_avatar)
async def profile_avatar_other(message: Message) -> None:
    await message.answer(strings.AVATAR_NEED_PHOTO)
