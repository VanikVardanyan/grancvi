"""Regression test for Task 30: /start update must propagate across routers.

Aiogram 3.x does NOT propagate to the next router when a matched handler returns
without raising SkipHandler. Filter-based gating ensures non-matching handlers
are skipped at filter level, allowing the update to reach the next router.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiogram import Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import Chat, Message, Update, User
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master
from src.handlers.admin.menu import IsAdminNoMaster
from src.handlers.master.start import HasInviteOrMaster


def _make_message(text: str = "/start") -> Message:
    return Message.model_validate(
        {
            "message_id": 1,
            "date": 1_700_000_000,
            "chat": Chat(id=100, type="private").model_dump(),
            "from": User(id=100, is_bot=False, first_name="T").model_dump(),
            "text": text,
        }
    )


def _make_update(message: Message) -> Update:
    return Update(update_id=1, message=message)


def _build_dispatcher(
    *,
    master: Master | None,
    is_admin: bool,
    session: AsyncSession | None = None,
) -> tuple[Dispatcher, dict[str, list[str]]]:
    captured: dict[str, list[str]] = {"calls": []}
    admin = Router(name="admin_stub")
    master_router = Router(name="master_stub")
    client = Router(name="client_stub")

    @admin.message(CommandStart(), IsAdminNoMaster())
    async def _admin_start(message: Message, **kwargs: Any) -> None:
        captured["calls"].append("admin")

    @master_router.message(CommandStart(), HasInviteOrMaster())
    async def _master_start(message: Message, **kwargs: Any) -> None:
        captured["calls"].append("master")

    @client.message(CommandStart())
    async def _client_start(message: Message, **kwargs: Any) -> None:
        captured["calls"].append("client")

    dp = Dispatcher()
    dp.include_router(admin)
    dp.include_router(master_router)
    dp.include_router(client)

    async def _inject(handler, event, data):  # type: ignore[no-untyped-def]
        data["master"] = master
        data["is_admin"] = is_admin
        data["session"] = session
        return await handler(event, data)

    dp.update.outer_middleware(_inject)
    return dp, captured


@pytest.mark.asyncio
async def test_admin_without_master_routes_to_admin() -> None:
    dp, captured = _build_dispatcher(master=None, is_admin=True)
    await dp.feed_update(bot=MagicMock(id=1), update=_make_update(_make_message()))
    assert captured["calls"] == ["admin"]


@pytest.mark.asyncio
async def test_admin_who_is_master_routes_to_master() -> None:
    master = Master(tg_id=100, name="A", slug="a-0001")
    dp, captured = _build_dispatcher(master=master, is_admin=True)
    await dp.feed_update(bot=MagicMock(id=1), update=_make_update(_make_message()))
    assert captured["calls"] == ["master"]


@pytest.mark.asyncio
async def test_master_non_admin_routes_to_master() -> None:
    master = Master(tg_id=100, name="A", slug="a-0001")
    dp, captured = _build_dispatcher(master=master, is_admin=False)
    await dp.feed_update(bot=MagicMock(id=1), update=_make_update(_make_message()))
    assert captured["calls"] == ["master"]


@pytest.mark.asyncio
async def test_pure_client_routes_to_client() -> None:
    dp, captured = _build_dispatcher(master=None, is_admin=False)
    await dp.feed_update(bot=MagicMock(id=1), update=_make_update(_make_message()))
    assert captured["calls"] == ["client"]


@pytest.mark.asyncio
async def test_client_with_invite_payload_routes_to_master(
    session: AsyncSession,
) -> None:
    """No master yet + master-kind invite payload → master router handles registration."""
    session.add(
        Invite(
            code="abc123",
            created_by_tg_id=1,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            kind="master",
        )
    )
    await session.commit()
    dp, captured = _build_dispatcher(master=None, is_admin=False, session=session)
    msg = _make_message("/start invite_abc123")
    await dp.feed_update(bot=MagicMock(id=1), update=_make_update(msg))
    assert captured["calls"] == ["master"]


@pytest.mark.asyncio
async def test_client_with_deep_link_routes_to_client() -> None:
    """No master, non-invite payload (master_<slug>) → client router."""
    dp, captured = _build_dispatcher(master=None, is_admin=False)
    msg = _make_message("/start master_somebody")
    await dp.feed_update(bot=MagicMock(id=1), update=_make_update(msg))
    assert captured["calls"] == ["client"]
