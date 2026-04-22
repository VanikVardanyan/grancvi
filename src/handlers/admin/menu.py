from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.handlers.admin.invites_admin import cmd_admin_invites
from src.handlers.admin.masters import cmd_admin_masters
from src.handlers.admin.moderation import cmd_admin_moderation
from src.handlers.admin.stats import cmd_admin_stats
from src.keyboards.common import main_menu
from src.strings import get_bundle, strings

router = Router(name="admin_menu")

_RU = get_bundle("ru")
_HY = get_bundle("hy")


@router.message(F.text.in_({_RU.ADMIN_MENU_MASTERS, _HY.ADMIN_MENU_MASTERS}))
async def handle_admin_masters(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_masters(message=message, session=session)


@router.message(F.text.in_({_RU.ADMIN_MENU_STATS, _HY.ADMIN_MENU_STATS}))
async def handle_admin_stats(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_stats(message=message, session=session)


@router.message(F.text.in_({_RU.ADMIN_MENU_INVITES, _HY.ADMIN_MENU_INVITES}))
async def handle_admin_invites(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_invites(message=message, session=session)


@router.message(F.text.in_({_RU.ADMIN_MENU_MODERATION, _HY.ADMIN_MENU_MODERATION}))
async def handle_admin_moderation(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_moderation(message=message, session=session)


@router.message(F.text.in_({_RU.ADMIN_MENU_BACK, _HY.ADMIN_MENU_BACK}))
async def handle_admin_back(message: Message, is_admin: bool = False) -> None:
    if not is_admin:
        return
    await message.answer(strings.START_WELCOME_BACK, reply_markup=main_menu())
