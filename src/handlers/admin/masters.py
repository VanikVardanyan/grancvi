from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.admin import block_toggle_kb, masters_list_kb
from src.repositories.masters import MasterRepository
from src.strings import strings

router = Router(name="admin_masters")


async def cmd_admin_masters(*, message: Message, session: AsyncSession) -> None:
    repo = MasterRepository(session)
    masters = await repo.list_all()
    if not masters:
        await message.answer(strings.ADMIN_MASTERS_EMPTY)
        return
    await message.answer(
        strings.ADMIN_MASTERS_HEADER, reply_markup=masters_list_kb(masters)
    )


async def cmd_admin_master_detail(
    *, message: Message, session: AsyncSession, slug: str
) -> None:
    repo = MasterRepository(session)
    master = await repo.by_slug(slug)
    if master is None:
        await message.answer(strings.ADMIN_MASTER_NOT_FOUND)
        return
    is_blocked = master.blocked_at is not None
    status = (
        strings.ADMIN_MASTER_STATUS_BLOCKED
        if is_blocked
        else strings.ADMIN_MASTER_STATUS_ACTIVE
    )
    text = (
        f"*{master.slug}* · {master.name}\n"
        f"Специальность: {master.specialty_text or '—'}\n"
        f"Статус: {status}\n"
        f"Зарегистрирован: {master.created_at.strftime('%Y-%m-%d')}"
    )
    await message.answer(text, reply_markup=block_toggle_kb(master))


@router.message(Command("masters"))
async def handle_masters_cmd(
    message: Message, session: AsyncSession, is_admin: bool = False
) -> None:
    if not is_admin:
        return
    await cmd_admin_masters(message=message, session=session)


@router.message(Command("master"))
async def handle_master_cmd(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return
    slug = (command.args or "").strip()
    if not slug:
        await message.answer("Usage: /master <slug>")
        return
    await cmd_admin_master_detail(message=message, session=session, slug=slug)
