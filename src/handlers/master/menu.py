from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from src.db.models import Master
from src.keyboards.settings import settings_menu
from src.strings import get_bundle, strings

router = Router(name="master_menu")

_RU_MENU = get_bundle("ru")
_HY_MENU = get_bundle("hy")


# Guard everything in this router by master presence — these buttons exist only
# for registered masters. If no master in data, let other routers handle it.
@router.message(F.text.in_({_RU_MENU.MAIN_MENU_TODAY, _HY_MENU.MAIN_MENU_TODAY}))
async def handle_today(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await message.answer(strings.STUB_TODAY)


@router.message(F.text.in_({_RU_MENU.MAIN_MENU_ADD, _HY_MENU.MAIN_MENU_ADD}))
async def handle_add(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await message.answer(strings.STUB_ADD)


@router.message(F.text.in_({_RU_MENU.MAIN_MENU_CALENDAR, _HY_MENU.MAIN_MENU_CALENDAR}))
async def handle_calendar(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await message.answer(strings.STUB_CALENDAR)


@router.message(F.text.in_({_RU_MENU.MAIN_MENU_SETTINGS, _HY_MENU.MAIN_MENU_SETTINGS}))
async def handle_settings(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await message.answer(strings.SETTINGS_MENU_TITLE, reply_markup=settings_menu())
