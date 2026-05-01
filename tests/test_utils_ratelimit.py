"""Sanity tests for the sliding-window rate-limit helper."""

from __future__ import annotations

import asyncio

import pytest
from redis.asyncio import Redis

from src.utils.ratelimit import consume_token


@pytest.mark.asyncio
async def test_consume_token_allows_under_limit() -> None:
    r = Redis.from_url("redis://localhost:6379/9", decode_responses=False)
    await r.delete("test:rl:under")
    for _ in range(3):
        assert await consume_token(r, "test:rl:under", limit=5, window_sec=10) is True
    await r.aclose()


@pytest.mark.asyncio
async def test_consume_token_blocks_over_limit() -> None:
    r = Redis.from_url("redis://localhost:6379/9", decode_responses=False)
    await r.delete("test:rl:over")
    for _ in range(3):
        assert await consume_token(r, "test:rl:over", limit=3, window_sec=10) is True
    # 4th request — over the limit
    assert await consume_token(r, "test:rl:over", limit=3, window_sec=10) is False
    await r.aclose()


@pytest.mark.asyncio
async def test_consume_token_window_resets() -> None:
    r = Redis.from_url("redis://localhost:6379/9", decode_responses=False)
    await r.delete("test:rl:reset")
    assert await consume_token(r, "test:rl:reset", limit=1, window_sec=1) is True
    assert await consume_token(r, "test:rl:reset", limit=1, window_sec=1) is False
    await asyncio.sleep(1.2)
    assert await consume_token(r, "test:rl:reset", limit=1, window_sec=1) is True
    await r.aclose()
