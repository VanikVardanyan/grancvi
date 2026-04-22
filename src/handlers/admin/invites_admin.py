from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

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


async def cmd_admin_invites(*, message: Message, session: AsyncSession) -> None:
    repo = InviteRepository(session)
    invites = await repo.list_all()
    if not invites:
        await message.answer(strings.MY_INVITES_EMPTY)
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
    await message.answer("\n".join(lines))


@router.message(Command("invites"))
async def handle_invites_cmd(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_invites(message=message, session=session)
