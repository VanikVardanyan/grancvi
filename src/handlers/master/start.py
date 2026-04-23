from __future__ import annotations

from datetime import UTC, datetime

import structlog
from aiogram import Router
from aiogram.filters import CommandStart, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.register import LangPickCallback
from src.db.models import Master
from src.fsm.master_register import MasterRegister
from src.handlers.client.start import start_booking_for_slug
from src.keyboards.common import lang_picker, main_menu
from src.repositories.invites import InviteRepository
from src.strings import set_current_lang, strings

router = Router(name="master_start")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


def _parse_invite_payload(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return None
    payload = parts[1]
    if not payload.startswith("invite_"):
        return None
    return payload[len("invite_") :]


def _parse_master_payload(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return None
    payload = parts[1]
    if not payload.startswith("master_"):
        return None
    return payload[len("master_") :]


class HasInviteOrMaster(Filter):
    async def __call__(
        self,
        event: Message,
        master: Master | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        if master is not None:
            return True
        code = _parse_invite_payload(event.text)
        if code is None or session is None:
            return False
        repo = InviteRepository(session)
        invite = await repo.by_code(code)
        return invite is not None and invite.kind == "master"


@router.message(CommandStart(), HasInviteOrMaster())
async def handle_start(
    message: Message,
    master: Master | None,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    tg_id = message.from_user.id if message.from_user else None
    invite_code = _parse_invite_payload(message.text)
    log.info(
        "start_received",
        tg_id=tg_id,
        has_master=master is not None,
        has_invite=invite_code is not None,
    )

    if invite_code is not None:
        if master is not None:
            await message.answer(strings.INVITE_ALREADY_MASTER)
            return
        repo = InviteRepository(session)
        invite = await repo.by_code(invite_code)
        if invite is None:
            await message.answer(strings.INVITE_NOT_FOUND)
            return
        if invite.used_at is not None:
            await message.answer(strings.INVITE_ALREADY_USED)
            return
        if invite.expires_at <= datetime.now(UTC):
            await message.answer(strings.INVITE_EXPIRED)
            return
        await state.clear()
        await state.update_data(invite_code=invite_code)
        await state.set_state(MasterRegister.waiting_lang)
        await message.answer(strings.LANG_PICK_PROMPT, reply_markup=lang_picker())
        return

    target_slug = _parse_master_payload(message.text)
    if master is not None and target_slug is not None and target_slug != master.slug:
        await start_booking_for_slug(
            slug=target_slug, message=message, state=state, session=session
        )
        return

    await state.clear()
    await message.answer(strings.START_WELCOME_BACK, reply_markup=main_menu())


@router.callback_query(LangPickCallback.filter(), MasterRegister.waiting_lang)
async def register_handle_lang(
    callback: CallbackQuery,
    callback_data: LangPickCallback,
    state: FSMContext,
) -> None:
    await state.update_data(lang=callback_data.lang)
    set_current_lang(callback_data.lang)
    await state.set_state(MasterRegister.waiting_name)
    await callback.answer()
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.REGISTER_WELCOME)
        await callback.message.answer(strings.REGISTER_ASK_NAME)


@router.message(MasterRegister.waiting_name)
async def register_handle_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(strings.REGISTER_ASK_NAME)
        return
    await state.update_data(name=name)
    await state.set_state(MasterRegister.waiting_phone)
    await message.answer(strings.REGISTER_ASK_PHONE)
