"""Simple per-key sliding-window rate-limit using Redis sorted sets.

`consume_token(key, limit, window_sec)` returns True if the request
fits in the window, False otherwise. Each call records `now` in the
sorted set; the oldest entries outside the window are pruned.

Designed for low-volume endpoints (public bookings) where a 1-2 ms
extra Redis round-trip is fine. Don't use for hot-path RPS.
"""

from __future__ import annotations

import time
import uuid

from redis.asyncio import Redis


async def consume_token(
    redis: Redis,
    key: str,
    *,
    limit: int,
    window_sec: int,
) -> bool:
    """Return True if request is allowed, False if over the limit.

    Sliding window: counts requests in the trailing `window_sec` seconds.
    Records the current request before counting so concurrent calls
    don't slip through.
    """
    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - window_sec * 1000
    # Member must be unique so concurrent requests in the same millisecond
    # don't overwrite each other in the sorted set.
    member = f"{now_ms}:{uuid.uuid4().hex}"

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, cutoff_ms)
    pipe.zadd(key, {member: now_ms})
    pipe.zcard(key)
    pipe.expire(key, window_sec)
    _, _, count, _ = await pipe.execute()

    return int(count) <= limit
