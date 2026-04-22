from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler


def build_scheduler() -> AsyncIOScheduler:
    """Build a bare AsyncIOScheduler.

    Uses the default (in-memory) jobstore: our only jobs are cron triggers
    re-registered on every process start, so persistence would add no value
    and the Bot/session_factory we inject via `functools.partial` are not
    picklable into a serialising jobstore anyway.

    Caller owns start/stop.
    """
    return AsyncIOScheduler(timezone="UTC")
