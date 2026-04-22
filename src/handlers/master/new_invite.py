from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import Master
from src.services.invite import InviteService
from src.strings import strings

router = Router(name="master_new_invite")


async def cmd_new_invite(
    *,
    message: Message,
    session: AsyncSession,
    master: Master,
) -> None:
    svc = InviteService(session)
    invite = await svc.create_invite(actor_tg_id=master.tg_id)
    link = f"https://t.me/{settings.bot_username}?start=invite_{invite.code}"
    text = strings.INVITE_CREATED_FMT.format(
        code=invite.code,
        link=link,
        expires=invite.expires_at.strftime("%Y-%m-%d %H:%M UTC"),
    )
    await message.answer(text)


@router.message(Command("new_invite"))
async def handle_new_invite_cmd(
    message: Message,
    session: AsyncSession,
    master: Master | None,
    is_admin: bool = False,
) -> None:
    if master is None and not is_admin:
        return
    if master is None:
        actor_tg = message.from_user.id if message.from_user else 0
        svc = InviteService(session)
        invite = await svc.create_invite(actor_tg_id=actor_tg)
        link = f"https://t.me/{settings.bot_username}?start=invite_{invite.code}"
        await message.answer(
            strings.INVITE_CREATED_FMT.format(
                code=invite.code,
                link=link,
                expires=invite.expires_at.strftime("%Y-%m-%d %H:%M UTC"),
            )
        )
        return
    await cmd_new_invite(message=message, session=session, master=master)
