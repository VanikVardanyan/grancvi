from __future__ import annotations

from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from src.config import settings


def build_fsm_storage() -> RedisStorage:
    """Build aiogram RedisStorage from settings.redis_url."""
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    return RedisStorage(redis=redis)
