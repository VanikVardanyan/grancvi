from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="sentry_debug")


@router.message(Command("sentrytest"))
async def handle_sentrytest(message: Message) -> None:
    await message.answer("Raising test exception for Sentry…")
    raise RuntimeError("epic-8-2 sentry smoke test")
