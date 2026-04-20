from __future__ import annotations

import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher

from src.config import settings
from src.db.base import SessionMaker
from src.fsm_storage import build_fsm_storage
from src.handlers import build_root_router
from src.middlewares.db import DbSessionMiddleware
from src.middlewares.lang import LangMiddleware
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


def build_dispatcher() -> Dispatcher:
    storage = build_fsm_storage()
    dp = Dispatcher(storage=storage)
    dp.update.middleware(DbSessionMiddleware(SessionMaker))
    dp.update.middleware(UserMiddleware())
    dp.update.middleware(LangMiddleware())
    dp.include_router(build_root_router())
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
