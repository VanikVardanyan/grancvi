from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.handlers.master.add_manual import cmd_add
from src.handlers.master.calendar import cmd_calendar
from src.handlers.master.today import cmd_today
from src.keyboards.settings import settings_menu
from src.strings import get_bundle, strings

router = Router(name="master_menu")

_RU_MENU = get_bundle("ru")
_HY_MENU = get_bundle("hy")


@router.message(F.text.in_({_RU_MENU.MAIN_MENU_TODAY, _HY_MENU.MAIN_MENU_TODAY}))
async def handle_today(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master | None,
) -> None:
    if master is None:
        return
    await cmd_today(message=message, state=state, session=session, master=master)


@router.message(F.text.in_({_RU_MENU.MAIN_MENU_ADD, _HY_MENU.MAIN_MENU_ADD}))
async def handle_add(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master | None,
) -> None:
    if master is None:
        return
    await cmd_add(message=message, state=state, session=session, master=master)


@router.message(F.text.in_({_RU_MENU.MAIN_MENU_CALENDAR, _HY_MENU.MAIN_MENU_CALENDAR}))
async def handle_calendar(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master | None,
) -> None:
    if master is None:
        return
    await cmd_calendar(message=message, state=state, session=session, master=master)


@router.message(F.text.in_({_RU_MENU.MAIN_MENU_SETTINGS, _HY_MENU.MAIN_MENU_SETTINGS}))
async def handle_settings(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await message.answer(strings.SETTINGS_MENU_TITLE, reply_markup=settings_menu())
