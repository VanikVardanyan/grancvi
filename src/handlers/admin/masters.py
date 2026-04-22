from __future__ import annotations

from aiogram import Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

router = Router(name="admin_masters")


async def cmd_admin_masters(*, message: Message, session: AsyncSession) -> None:
    await message.answer("masters (stub)")
