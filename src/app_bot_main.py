"""Entry point for the TMA launcher bot (@grancviWebBot).

Runs as a separate container from the main bot. Its only job is to
listen for /start and reply with a WebApp-launcher button. No DB access,
no FSM, no scheduler — everything else happens in the mini-app.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import structlog
from aiogram import Bot, Dispatcher

from src.app_bot.handlers import router as app_bot_router
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


async def main() -> None:
    configure_logging()
    log: structlog.stdlib.BoundLogger = structlog.get_logger()

    if not settings.app_bot_token:
        log.error("app_bot_token_missing")
        sys.exit(1)

    bot = Bot(token=settings.app_bot_token)
    dp = Dispatcher()
    dp.include_router(app_bot_router)

    log.info("app_bot_starting")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
