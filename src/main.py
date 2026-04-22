from __future__ import annotations

import asyncio
import logging
from functools import partial

import structlog
from aiogram import Bot, Dispatcher
from apscheduler.triggers.cron import CronTrigger

from src.config import settings
from src.db.base import SessionMaker
from src.fsm_storage import build_fsm_storage
from src.handlers import build_root_router
from src.middlewares.db import DbSessionMiddleware
from src.middlewares.lang import LangMiddleware
from src.middlewares.user import UserMiddleware
from src.scheduler.jobs import expire_pending_appointments, send_due_reminders
from src.scheduler.setup import build_scheduler


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


def _init_sentry_if_configured(dsn: str | None) -> None:
    if not dsn:
        return
    import sentry_sdk

    sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)


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
    _init_sentry_if_configured(settings.sentry_dsn)
    bot = Bot(token=settings.bot_token)
    dp = build_dispatcher()

    scheduler = build_scheduler()
    scheduler.add_job(
        partial(send_due_reminders, bot=bot, session_factory=SessionMaker),
        trigger=CronTrigger(minute="*"),
        id="send_due_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        partial(expire_pending_appointments, bot=bot, session_factory=SessionMaker),
        trigger=CronTrigger(minute="*/5"),
        id="expire_pending_appointments",
        replace_existing=True,
    )

    log.info("bot_starting")
    scheduler.start()
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
