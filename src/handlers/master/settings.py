from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.settings import LanguageCallback, SettingsCallback, WorkHoursDay
from src.db.models import Master
from src.fsm.work_hours import WorkHoursEdit
from src.handlers.master.my_invites import cmd_myinvites
from src.handlers.master.new_invite import cmd_new_invite
from src.handlers.master.profile import open_profile_menu
from src.keyboards.services import services_list
from src.keyboards.settings import language_menu, work_hours_day_prompt, work_hours_list
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.strings import set_current_lang, strings
from src.utils.work_hours import (
    InvalidTimeFormat,
    InvalidTimeOrder,
    parse_hhmm,
    set_day_hours,
    set_day_off,
)

router = Router(name="master_settings")


async def _render_work_hours(target: Message, master: Master) -> None:
    await target.answer(strings.WORK_HOURS_TITLE, reply_markup=work_hours_list(master.work_hours))


@router.callback_query(SettingsCallback.filter(F.section == "my_invites"))
async def on_my_invites(
    cb: CallbackQuery,
    session: AsyncSession,
    master: Master | None,
) -> None:
    if master is None or cb.message is None:
        await cb.answer()
        return
    await cmd_myinvites(message=cb.message, session=session, master=master)
    await cb.answer()


@router.callback_query(SettingsCallback.filter(F.section == "new_invite"))
async def on_new_invite(
    cb: CallbackQuery,
    session: AsyncSession,
    master: Master | None,
) -> None:
    if master is None or cb.message is None:
        await cb.answer()
        return
    await cmd_new_invite(message=cb.message, session=session, master=master)
    await cb.answer()


@router.callback_query(SettingsCallback.filter(F.section == "profile"))
async def on_profile(
    cb: CallbackQuery,
    master: Master | None,
    state: FSMContext,
) -> None:
    if master is None or cb.message is None:
        await cb.answer()
        return
    await open_profile_menu(message=cb.message, state=state, master=master)
    await cb.answer()


@router.callback_query(SettingsCallback.filter())
async def handle_settings_section(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await callback.answer()
        return

    if callback_data.section == "services":
        repo = ServiceRepository(session)
        svcs = await repo.list_active(master.id)
        await callback.answer()
        if isinstance(callback.message, Message):
            title = strings.SERVICES_LIST_TITLE if svcs else strings.SERVICES_EMPTY
            await callback.message.answer(title, reply_markup=services_list(svcs))
        return

    if callback_data.section == "hours":
        await callback.answer()
        if isinstance(callback.message, Message):
            await _render_work_hours(callback.message, master)
        return

    if callback_data.section == "language":
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(
                strings.LANGUAGE_PICK_PROMPT, reply_markup=language_menu()
            )
        return

    # breaks wired later (out of scope for this epic)
    await callback.answer(strings.SECTION_COMING_SOON.format(section=callback_data.section))


@router.callback_query(WorkHoursDay.filter(F.action == "pick"))
async def cb_pick_day(
    callback: CallbackQuery,
    callback_data: WorkHoursDay,
    state: FSMContext,
) -> None:
    await state.set_state(WorkHoursEdit.waiting_start)
    await state.update_data(day=callback_data.day)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            strings.WORK_HOURS_ASK_START,
            reply_markup=work_hours_day_prompt(callback_data.day),
        )


@router.callback_query(WorkHoursDay.filter(F.action == "day_off"))
async def cb_day_off(
    callback: CallbackQuery,
    callback_data: WorkHoursDay,
    state: FSMContext,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await callback.answer()
        return
    await state.clear()
    updated = set_day_off(master.work_hours, callback_data.day)
    repo = MasterRepository(session)
    await repo.update_work_hours(master.id, updated)
    master.work_hours = updated
    await callback.answer(strings.WORK_HOURS_SAVED)
    if isinstance(callback.message, Message):
        await _render_work_hours(callback.message, master)


@router.callback_query(WorkHoursDay.filter(F.action == "done"))
async def cb_work_hours_done(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer(strings.WORK_HOURS_SAVED)


@router.message(WorkHoursEdit.waiting_start)
async def wh_handle_start(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    try:
        parse_hhmm(raw)
    except InvalidTimeFormat:
        await message.answer(strings.WORK_HOURS_BAD_FORMAT)
        return
    await state.update_data(start=raw)
    await state.set_state(WorkHoursEdit.waiting_end)
    await message.answer(strings.WORK_HOURS_ASK_END)


@router.callback_query(LanguageCallback.filter())
async def cb_pick_language(
    callback: CallbackQuery,
    callback_data: LanguageCallback,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await callback.answer()
        return
    repo = MasterRepository(session)
    await repo.update_lang(master.id, callback_data.lang)
    master.lang = callback_data.lang
    set_current_lang(callback_data.lang)
    await callback.answer(strings.LANGUAGE_CHANGED)


@router.message(WorkHoursEdit.waiting_end)
async def wh_handle_end(
    message: Message,
    state: FSMContext,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await state.clear()
        return
    raw_end = (message.text or "").strip()
    data = await state.get_data()
    day: str = data["day"]
    raw_start: str = data["start"]
    try:
        updated = set_day_hours(master.work_hours, day, raw_start, raw_end)
    except InvalidTimeFormat:
        await message.answer(strings.WORK_HOURS_BAD_FORMAT)
        return
    except InvalidTimeOrder:
        await message.answer(strings.WORK_HOURS_BAD_ORDER)
        return

    repo = MasterRepository(session)
    await repo.update_work_hours(master.id, updated)
    master.work_hours = updated
    await state.clear()
    await message.answer(strings.WORK_HOURS_SAVED)
    await _render_work_hours(message, master)
