from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.scheduler.setup import build_scheduler


def test_build_scheduler_returns_scheduler_not_running() -> None:
    sched = build_scheduler()
    assert isinstance(sched, AsyncIOScheduler)
    assert sched.running is False
