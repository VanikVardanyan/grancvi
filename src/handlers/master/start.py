from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.register import LangPickCallback
from src.config import settings
from src.db.models import Client, Master
from src.fsm.master_register import MasterRegister
from src.keyboards.common import lang_picker, main_menu
from src.repositories.masters import MasterRepository
from src.strings import set_current_lang, strings

router = Router(name="master_start")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


@router.message(CommandStart())
async def handle_start(
    message: Message,
    master: Master | None,
    client: Client | None,
    state: FSMContext,
) -> None:
    tg_id = message.from_user.id if message.from_user else None
    log.info(
        "start_received",
        tg_id=tg_id,
        has_master=master is not None,
        has_client=client is not None,
    )

    if master is not None:
        await state.clear()
        await message.answer(strings.START_WELCOME_BACK, reply_markup=main_menu())
        return

    if tg_id is not None and tg_id in settings.admin_tg_ids:
        await state.set_state(MasterRegister.waiting_lang)
        await message.answer(strings.LANG_PICK_PROMPT, reply_markup=lang_picker())
        return

    if client is not None:
        await message.answer(strings.CLIENT_STUB)
        return

    await message.answer(strings.START_UNKNOWN)


@router.callback_query(LangPickCallback.filter(), MasterRegister.waiting_lang)
async def register_handle_lang(
    callback: CallbackQuery,
    callback_data: LangPickCallback,
    state: FSMContext,
) -> None:
    # Persist the picked language in FSM data, and flip the request's ContextVar so
    # the very next message we send already uses the chosen bundle.
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


@router.message(MasterRegister.waiting_phone)
async def register_handle_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    phone = (message.text or "").strip()
    if not phone:
        await message.answer(strings.REGISTER_ASK_PHONE)
        return
    if message.from_user is None:
        await state.clear()
        return

    data = await state.get_data()
    name: str = data["name"]
    lang: str = data.get("lang", "ru")
    # Keep the ContextVar aligned for the final confirmation message in this request.
    set_current_lang(lang)

    repo = MasterRepository(session)
    await repo.create(tg_id=message.from_user.id, name=name, phone=phone, lang=lang)

    await state.clear()
    await message.answer(strings.REGISTER_DONE, reply_markup=main_menu())
