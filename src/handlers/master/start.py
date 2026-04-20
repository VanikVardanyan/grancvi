from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="master_start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await message.answer("hello")
