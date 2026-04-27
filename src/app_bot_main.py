"""Entry point for the TMA launcher bot (@grancviWebBot).

Owns the Telegram side of the stack now that the legacy @GrancviBot
has been retired: handles /start, runs the reminder scheduler, and
sends all user-facing notifications that originate server-side.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from functools import partial

import structlog
from aiogram import Bot, Dispatcher
from aiogram.types import MenuButtonWebApp, WebAppInfo
from apscheduler.triggers.cron import CronTrigger

from src.app_bot.approval import router as approval_router
from src.app_bot.handlers import router as app_bot_router
from src.config import settings
from src.db.base import SessionMaker
from src.scheduler.jobs import expire_pending_appointments, send_due_reminders
from src.scheduler.setup import build_scheduler

_TMA_URL = settings.tma_url
_MENU_BUTTON_TEXT = "Open App"


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


def _init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(dsn=settings.sentry_dsn, traces_sample_rate=0.0, send_default_pii=False)


async def main() -> None:
    configure_logging()
    _init_sentry()
    log: structlog.stdlib.BoundLogger = structlog.get_logger()

    if not settings.app_bot_token:
        log.error("app_bot_token_missing")
        sys.exit(1)

    bot = Bot(token=settings.app_bot_token)
    dp = Dispatcher()
    dp.include_router(app_bot_router)
    dp.include_router(approval_router)

    # Default menu button (next to the message input) opens the TMA in one tap.
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text=_MENU_BUTTON_TEXT, web_app=WebAppInfo(url=_TMA_URL))
        )
    except Exception as exc:
        log.warning("set_menu_button_failed", err=repr(exc))

    # Reminder + pending-expiry jobs. Both pass `app_bot` as both the
    # primary and the fallback since the legacy bot is gone — the
    # notify_user helper still works with identical bots, it just skips
    # the fallback branch on success.
    scheduler = build_scheduler()
    scheduler.add_job(
        partial(send_due_reminders, bot=bot, app_bot=bot, session_factory=SessionMaker),
        trigger=CronTrigger(minute="*"),
        id="send_due_reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        partial(
            expire_pending_appointments,
            bot=bot,
            app_bot=bot,
            session_factory=SessionMaker,
        ),
        trigger=CronTrigger(minute="*/5"),
        id="expire_pending_appointments",
        replace_existing=True,
    )

    log.info("app_bot_starting")
    scheduler.start()
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=True)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
