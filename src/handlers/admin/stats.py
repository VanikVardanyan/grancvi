from __future__ import annotations

from aiogram import Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

router = Router(name="admin_stats")


async def cmd_admin_stats(*, message: Message, session: AsyncSession) -> None:
    await message.answer("stats (stub)")
