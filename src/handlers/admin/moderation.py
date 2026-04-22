from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.masters import MasterRepository
from src.services.moderation import ModerationService
from src.strings import strings

router = Router(name="admin_moderation")


async def cmd_admin_moderation(*, message: Message, session: AsyncSession) -> None:
    await message.answer(strings.ADMIN_MENU_MODERATION)


async def cmd_block_master(
    *,
    message: Message,
    session: AsyncSession,
    slug: str,
    bot: Bot,
) -> None:
    repo = MasterRepository(session)
    master = await repo.by_slug(slug)
    if master is None:
        await message.answer(strings.ADMIN_MASTER_NOT_FOUND)
        return
    svc = ModerationService(session)
    result = await svc.block_master(master.id)
    for info in result.rejected:
        if info.client_tg_id is not None:
            await bot.send_message(info.client_tg_id, strings.CLIENT_APPT_REJECTED_BLOCK)
    await message.answer(strings.ADMIN_BLOCK_DONE_FMT.format(slug=slug, n=len(result.rejected)))


async def cmd_unblock_master(
    *,
    message: Message,
    session: AsyncSession,
    slug: str,
) -> None:
    repo = MasterRepository(session)
    master = await repo.by_slug(slug)
    if master is None:
        await message.answer(strings.ADMIN_MASTER_NOT_FOUND)
        return
    svc = ModerationService(session)
    await svc.unblock_master(master.id)
    await message.answer(strings.ADMIN_UNBLOCK_DONE_FMT.format(slug=slug))


@router.message(Command("block"))
async def handle_block_cmd(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    bot: Bot,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return
    slug = (command.args or "").strip()
    if not slug:
        await message.answer("/block <slug>")
        return
    await cmd_block_master(message=message, session=session, slug=slug, bot=bot)


@router.message(Command("unblock"))
async def handle_unblock_cmd(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        return
    slug = (command.args or "").strip()
    if not slug:
        await message.answer("/unblock <slug>")
        return
    await cmd_unblock_master(message=message, session=session, slug=slug)
