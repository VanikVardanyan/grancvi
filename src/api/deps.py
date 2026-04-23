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
