from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from src.config import settings
from src.db.models import Master
from src.strings import strings
from src.utils.qr import build_master_qr

router = Router(name="master_my_link")


def _master_link(master: Master) -> str:
    return f"https://t.me/{settings.bot_username}?start=master_{master.slug}"


async def cmd_mylink(*, message: Message, master: Master) -> None:
    await message.answer(strings.MY_LINK_MSG_FMT.format(link=_master_link(master)))


async def cmd_qr(*, message: Message, master: Master) -> None:
    link = _master_link(master)
    png = build_master_qr(link)
    photo = BufferedInputFile(png, filename=f"qr-{master.slug}.png")
    await message.answer_photo(photo=photo, caption=strings.QR_CAPTION_FMT.format(link=link))


@router.message(Command("mylink"))
async def handle_mylink_cmd(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await cmd_mylink(message=message, master=master)


@router.message(Command("qr"))
async def handle_qr_cmd(message: Message, master: Master | None) -> None:
    if master is None:
        return
    await cmd_qr(message=message, master=master)
