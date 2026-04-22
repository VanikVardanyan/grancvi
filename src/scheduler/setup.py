from __future__ import annotations

from urllib.parse import urlparse

from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler


def build_scheduler(redis_url: str) -> AsyncIOScheduler:
    """Build AsyncIOScheduler with RedisJobStore from a `redis://host:port/db` URL.

    The scheduler is not started — caller owns start/stop.
    """
    parsed = urlparse(redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    db = int((parsed.path or "/0").lstrip("/") or 0)

    jobstores = {"default": RedisJobStore(host=host, port=port, db=db)}
    return AsyncIOScheduler(jobstores=jobstores, timezone="UTC")
