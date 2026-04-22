from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.config import settings
from src.db.models import Master
from src.strings import strings

router = Router(name="master_my_link")


async def cmd_mylink(*, message: Message, master: Master) -> None:
    link = f"https://t.me/{settings.bot_username}?start=master_{master.slug}"
    await message.answer(strings.MY_LINK_MSG_FMT.format(link=link))


@router.message(Command("mylink"))
async def handle_mylink_cmd(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await cmd_mylink(message=message, master=master)
