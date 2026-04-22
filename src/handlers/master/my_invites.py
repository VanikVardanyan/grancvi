from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master
from src.repositories.invites import InviteRepository
from src.strings import strings

router = Router(name="master_my_invites")


def _format_status(invite: Invite) -> str:
    if invite.used_at is not None:
        return strings.MY_INVITES_STATUS_USED
    if invite.expires_at <= datetime.now(timezone.utc):
        return strings.MY_INVITES_STATUS_EXPIRED
    return strings.MY_INVITES_STATUS_ACTIVE


async def cmd_myinvites(
    *,
    message: Message,
    session: AsyncSession,
    master: Master,
) -> None:
    repo = InviteRepository(session)
    invites = await repo.list_by_creator(master.tg_id)
    if not invites:
        await message.answer(strings.MY_INVITES_EMPTY)
        return
    lines = [strings.MY_INVITES_HEADER]
    for inv in invites:
        lines.append(
            strings.MY_INVITES_ITEM_FMT.format(
                code=inv.code,
                status=_format_status(inv),
                expires=inv.expires_at.strftime("%Y-%m-%d"),
            )
        )
    await message.answer("\n".join(lines))


@router.message(Command("myinvites"))
async def handle_myinvites_cmd(
    message: Message,
    session: AsyncSession,
    master: Master | None,
) -> None:
    if master is None:
        return
    await cmd_myinvites(message=message, session=session, master=master)
