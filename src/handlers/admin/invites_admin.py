from __future__ import annotations

from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.admin import AdminNewSalonCallback
from src.config import settings
from src.db.models import Invite
from src.repositories.invites import InviteRepository
from src.strings import strings
from src.utils.time import now_utc

router = Router(name="admin_invites")


def _status(inv: Invite) -> str:
    if inv.used_at is not None:
        return str(strings.MY_INVITES_STATUS_USED)
    if inv.expires_at <= now_utc():
        return str(strings.MY_INVITES_STATUS_EXPIRED)
    return str(strings.MY_INVITES_STATUS_ACTIVE)


def _admin_invites_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.ADMIN_INVITE_NEW_SALON_BTN,
                    callback_data=AdminNewSalonCallback().pack(),
                )
            ]
        ]
    )


async def cmd_admin_invites(*, message: Message, session: AsyncSession) -> None:
    repo = InviteRepository(session)
    invites = await repo.list_all()
    if not invites:
        await message.answer(strings.MY_INVITES_EMPTY, reply_markup=_admin_invites_kb())
        return
    lines = [strings.ADMIN_INVITES_HEADER]
    for inv in invites:
        lines.append(
            strings.ADMIN_INVITE_ITEM_FMT.format(
                code=inv.code,
                status=_status(inv),
                creator_tg_id=inv.created_by_tg_id,
            )
        )
    await message.answer("\n".join(lines), reply_markup=_admin_invites_kb())


@router.message(Command("invites"))
async def handle_invites_cmd(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_invites(message=message, session=session)


@router.callback_query(AdminNewSalonCallback.filter())
async def cb_admin_new_salon(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    tg_id = callback.from_user.id if callback.from_user else 0
    repo = InviteRepository(session)
    invite = await repo.create(created_by_tg_id=tg_id, kind="salon_owner")
    await session.commit()

    link = f"https://t.me/{settings.bot_username}?start=invite_{invite.code}"
    tz = ZoneInfo("Asia/Yerevan")
    expires_local = invite.expires_at.astimezone(tz).strftime("%d.%m.%Y %H:%M")

    text = strings.ADMIN_INVITE_SALON_CREATED_FMT.format(
        code=invite.code, link=link, expires=expires_local
    )
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(text, parse_mode="Markdown")
