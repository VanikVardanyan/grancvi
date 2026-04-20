from __future__ import annotations

import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from src.config import settings


def configure_logging() -> None:
    logging.basicConfig(level=settings.log_level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


log: structlog.stdlib.BoundLogger = structlog.get_logger()


async def handle_start(message: Message) -> None:
    await message.answer("hello")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.register(handle_start, CommandStart())
    return dp


async def main() -> None:
    configure_logging()
    bot = Bot(token=settings.bot_token)
    dp = build_dispatcher()
    log.info("bot_starting")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
