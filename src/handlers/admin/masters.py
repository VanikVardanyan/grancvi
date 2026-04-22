from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.admin import AdminMasterCallback, BlockCallback
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
    await message.answer(strings.ADMIN_MASTERS_HEADER, reply_markup=masters_list_kb(masters))


async def cmd_admin_master_detail(*, message: Message, session: AsyncSession, slug: str) -> None:
    repo = MasterRepository(session)
    master = await repo.by_slug(slug)
    if master is None:
        await message.answer(strings.ADMIN_MASTER_NOT_FOUND)
        return
    is_blocked = master.blocked_at is not None
    status = (
        strings.ADMIN_MASTER_STATUS_BLOCKED if is_blocked else strings.ADMIN_MASTER_STATUS_ACTIVE
    )
    text = (
        f"{master.slug} · {master.name}\n"
        f"{strings.ADMIN_MASTER_DETAIL_SPECIALTY}: {master.specialty_text or '—'}\n"
        f"{strings.ADMIN_MASTER_DETAIL_STATUS}: {status}\n"
        f"{strings.ADMIN_MASTER_DETAIL_REGISTERED}: {master.created_at.strftime('%Y-%m-%d')}"
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
        await message.answer(strings.ADMIN_MASTER_USAGE)
        return
    await cmd_admin_master_detail(message=message, session=session, slug=slug)


@router.callback_query(AdminMasterCallback.filter(F.action == "view"))
async def handle_admin_master_view(
    callback: CallbackQuery,
    callback_data: AdminMasterCallback,
    session: AsyncSession,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer()
        return
    repo = MasterRepository(session)
    master = await repo.by_id(callback_data.master_id)
    if master is None:
        await callback.answer(strings.ADMIN_MASTER_NOT_FOUND, show_alert=True)
        return
    is_blocked = master.blocked_at is not None
    status = (
        strings.ADMIN_MASTER_STATUS_BLOCKED if is_blocked else strings.ADMIN_MASTER_STATUS_ACTIVE
    )
    text = (
        f"{master.slug} · {master.name}\n"
        f"{strings.ADMIN_MASTER_DETAIL_SPECIALTY}: {master.specialty_text or '—'}\n"
        f"{strings.ADMIN_MASTER_DETAIL_STATUS}: {status}\n"
        f"{strings.ADMIN_MASTER_DETAIL_REGISTERED}: {master.created_at.strftime('%Y-%m-%d')}"
    )
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=block_toggle_kb(master))
    await callback.answer()


@router.callback_query(BlockCallback.filter())
async def handle_block_toggle(
    callback: CallbackQuery,
    callback_data: BlockCallback,
    session: AsyncSession,
    bot: Bot,
    is_admin: bool = False,
) -> None:
    if not is_admin:
        await callback.answer()
        return
    from src.handlers.admin.moderation import cmd_block_master, cmd_unblock_master

    repo = MasterRepository(session)
    master = await repo.by_id(callback_data.master_id)
    if master is None:
        await callback.answer(strings.ADMIN_MASTER_NOT_FOUND, show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer()
        return
    if callback_data.block:
        await cmd_block_master(
            message=callback.message,
            session=session,
            slug=master.slug,
            bot=bot,
        )
    else:
        await cmd_unblock_master(
            message=callback.message,
            session=session,
            slug=master.slug,
        )
    await callback.answer()
