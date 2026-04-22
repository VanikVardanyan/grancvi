from __future__ import annotations

from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.scheduler.setup import build_scheduler


def test_build_scheduler_uses_redis_jobstore_from_url() -> None:
    sched = build_scheduler("redis://localhost:6379/0")
    assert isinstance(sched, AsyncIOScheduler)
    default_store = sched._jobstores["default"]  # type: ignore[attr-defined]
    assert isinstance(default_store, RedisJobStore)


def test_build_scheduler_returns_scheduler_not_running() -> None:
    sched = build_scheduler("redis://localhost:6379/0")
    assert sched.running is False
