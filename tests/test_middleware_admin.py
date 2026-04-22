from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import patch

import pytest
from aiogram.types import TelegramObject

from src.middlewares.admin import AdminMiddleware


@dataclass
class FakeUser:
    id: int


@dataclass
class FakeEvent:
    from_user: FakeUser | None


@pytest.mark.asyncio
async def test_admin_flag_true_for_admin_tg_id() -> None:
    middleware = AdminMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    with patch("src.middlewares.admin.settings") as mocked:
        mocked.admin_tg_ids = [100]
        await middleware(
            handler,
            cast(TelegramObject, FakeEvent(from_user=FakeUser(id=100))),
            {},
        )
    assert captured["is_admin"] is True


@pytest.mark.asyncio
async def test_admin_flag_false_for_non_admin() -> None:
    middleware = AdminMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    with patch("src.middlewares.admin.settings") as mocked:
        mocked.admin_tg_ids = [100]
        await middleware(
            handler,
            cast(TelegramObject, FakeEvent(from_user=FakeUser(id=200))),
            {},
        )
    assert captured["is_admin"] is False


@pytest.mark.asyncio
async def test_admin_flag_false_without_user() -> None:
    middleware = AdminMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured.update(data)

    with patch("src.middlewares.admin.settings") as mocked:
        mocked.admin_tg_ids = [100]
        await middleware(
            handler,
            cast(TelegramObject, FakeEvent(from_user=None)),
            {},
        )
    assert captured["is_admin"] is False
