from __future__ import annotations

from collections.abc import AsyncGenerator

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.base import SessionMaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession bound to the shared engine.

    Mirrors the middleware used by the bot — tests override this to inject a
    session backed by the test database.
    """
    async with SessionMaker() as s:
        yield s


async def get_bot() -> AsyncGenerator[Bot, None]:
    """Yield an aiogram Bot configured with the legacy `bot_token`.

    Used for master notifications from API write paths. Constructed per-request
    for MVP simplicity — tests override this to inject a mock.
    """
    bot = Bot(token=settings.bot_token)
    try:
        yield bot
    finally:
        await bot.session.close()


async def get_app_bot() -> AsyncGenerator[Bot | None, None]:
    """Yield an aiogram Bot for @grancviWebBot (TMA launcher), or None.

    None is returned when app_bot_token isn't configured — callers fall
    back to the legacy bot. Using two separate clients lets us prefer
    the new bot for notifications while keeping legacy ones alive for
    users who haven't opened the new bot yet.
    """
    if not settings.app_bot_token:
        yield None
        return
    bot = Bot(token=settings.app_bot_token)
    try:
        yield bot
    finally:
        await bot.session.close()
