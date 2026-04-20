from __future__ import annotations

import asyncio
import logging
from typing import Any

import structlog
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message

from src.config import settings
from src.db.base import SessionMaker
from src.db.models import Client, Master
from src.middlewares.db import DbSessionMiddleware
from src.middlewares.user import UserMiddleware


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


async def handle_start(
    message: Message,
    master: Master | None,
    client: Client | None,
    **_: Any,
) -> None:
    log.info(
        "start_received",
        tg_id=message.from_user.id if message.from_user else None,
        has_master=master is not None,
        has_client=client is not None,
    )
    await message.answer("hello")


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.update.middleware(DbSessionMiddleware(SessionMaker))
    dp.update.middleware(UserMiddleware())
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
