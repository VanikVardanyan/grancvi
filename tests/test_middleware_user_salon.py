from __future__ import annotations

from typing import Any

import pytest
from aiogram.types import Chat, Message, Update, User
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Salon
from src.middlewares.user import UserMiddleware


def _mk_update(user_id: int) -> Update:
    user = User(id=user_id, is_bot=False, first_name="U")
    chat = Chat(id=user_id, type="private")
    msg = Message.model_construct(
        message_id=1,
        date=0,  # type: ignore[arg-type]
        chat=chat,
        from_user=user,
        text="/start",
    )
    return Update.model_construct(update_id=1, message=msg)


@pytest.mark.asyncio
async def test_user_middleware_populates_salon_when_owner(session: AsyncSession) -> None:
    session.add(Salon(owner_tg_id=500, name="S", slug="s-own"))
    await session.commit()

    mw = UserMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured["salon"] = data.get("salon")
        captured["master"] = data.get("master")

    await mw(handler, _mk_update(user_id=500), {"session": session})
    assert captured["master"] is None
    assert captured["salon"] is not None
    assert captured["salon"].owner_tg_id == 500


@pytest.mark.asyncio
async def test_user_middleware_salon_none_when_not_owner(session: AsyncSession) -> None:
    mw = UserMiddleware()
    captured: dict[str, Any] = {}

    async def handler(event: Any, data: dict[str, Any]) -> None:
        captured["salon"] = data.get("salon")

    await mw(handler, _mk_update(user_id=9999), {"session": session})
    assert captured["salon"] is None
