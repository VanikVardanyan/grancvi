from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.registration import SlugConfirmCallback, SpecialtyHintCallback
from src.config import settings
from src.exceptions import InvalidSlug, ReservedSlug, SlugTaken
from src.fsm.master_register import MasterRegister
from src.keyboards.common import main_menu
from src.keyboards.registration import slug_confirm_kb, specialty_hints_kb
from src.repositories.masters import MasterRepository
from src.services.master_registration import MasterRegistrationService
from src.services.slug import SlugService
from src.strings import set_current_lang, strings

router = Router(name="master_registration_v2")


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
    await state.update_data(phone=phone)
    await state.set_state(MasterRegister.waiting_specialty)
    await message.answer(strings.REGISTER_ASK_SPECIALTY, reply_markup=specialty_hints_kb())


_HINT_MAP = {
    "hair": "REGISTER_SPECIALTY_HINT_HAIR",
    "dentist": "REGISTER_SPECIALTY_HINT_DENTIST",
    "nails": "REGISTER_SPECIALTY_HINT_NAILS",
    "cosmetologist": "REGISTER_SPECIALTY_HINT_COSMETOLOGIST",
    "custom": "REGISTER_SPECIALTY_HINT_CUSTOM",
}


@router.callback_query(SpecialtyHintCallback.filter(), MasterRegister.waiting_specialty)
async def register_handle_specialty_hint(
    cb: CallbackQuery,
    callback_data: SpecialtyHintCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback_data.hint == "custom":
        await cb.answer()
        if cb.message is not None:
            await cb.message.answer(strings.REGISTER_ASK_SPECIALTY)
        return
    label = getattr(strings, _HINT_MAP[callback_data.hint])
    stripped = label.split(" ", 1)[1] if " " in label else label
    msg = cb.message if isinstance(cb.message, Message) else None
    await _accept_specialty(specialty=stripped, state=state, session=session, message=msg)
    await cb.answer()


@router.message(MasterRegister.waiting_specialty)
async def register_handle_specialty_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    specialty = (message.text or "").strip()
    if not specialty:
        await message.answer(strings.REGISTER_ASK_SPECIALTY)
        return
    await _accept_specialty(specialty=specialty, state=state, session=session, message=message)


async def _accept_specialty(
    *,
    specialty: str,
    state: FSMContext,
    session: AsyncSession,
    message: Message | None,
) -> None:
    await state.update_data(specialty=specialty)
    data = await state.get_data()
    name: str = data.get("name", "")
    slug_svc = SlugService(session)
    slug = await slug_svc.generate_default(name)
    await state.update_data(proposed_slug=slug)
    await state.set_state(MasterRegister.waiting_slug_confirm)
    if message is not None:
        await message.answer(
            strings.REGISTER_SLUG_CONFIRM_FMT.format(slug=slug, username=settings.bot_username),
            reply_markup=slug_confirm_kb(),
        )


@router.callback_query(SlugConfirmCallback.filter(), MasterRegister.waiting_slug_confirm)
async def register_handle_slug_confirm(
    cb: CallbackQuery,
    callback_data: SlugConfirmCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await cb.answer()
    if callback_data.action == "change":
        await state.set_state(MasterRegister.waiting_custom_slug)
        if cb.message is not None:
            await cb.message.answer(strings.REGISTER_ASK_CUSTOM_SLUG)
        return
    data = await state.get_data()
    slug = data["proposed_slug"]
    await _finalize(slug=slug, state=state, session=session, cb=cb)


@router.message(MasterRegister.waiting_custom_slug)
async def register_handle_custom_slug(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
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
    if await repo.by_slug(slug) is not None:
        await message.answer(strings.REGISTER_SLUG_TAKEN)
        return

    await _finalize(slug=slug, state=state, session=session, message=message)


async def _finalize(
    *,
    slug: str,
    state: FSMContext,
    session: AsyncSession,
    cb: CallbackQuery | None = None,
    message: Message | None = None,
) -> None:
    data = await state.get_data()
    out_message: Message | None = message
    if out_message is None and cb is not None and cb.message is not None:
        out_message = cb.message  # type: ignore[assignment]

    tg_id: int | None = None
    if cb is not None and cb.from_user is not None:
        tg_id = cb.from_user.id
    elif message is not None and message.from_user is not None:
        tg_id = message.from_user.id
    if tg_id is None:
        await state.clear()
        return

    set_current_lang(data.get("lang", "ru"))

    svc = MasterRegistrationService(session)
    try:
        await svc.register(
            tg_id=tg_id,
            name=data["name"],
            specialty=data["specialty"],
            slug=slug,
            lang=data.get("lang", "ru"),
            invite_code=data["invite_code"],
        )
        await session.commit()
    except SlugTaken:
        if out_message is not None:
            await out_message.answer(strings.REGISTER_SLUG_TAKEN)
        return

    await state.clear()
    if out_message is not None:
        await out_message.answer(strings.REGISTER_DONE, reply_markup=main_menu())
