from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.schedule import DayNavCallback
from src.db.models import Appointment, Client, Master, Service
from src.handlers.master._common import safe_edit
from src.handlers.master.today import cb_day_nav, cmd_today, cmd_tomorrow


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMsg:
    from_user: _FakeUser | None = None
    answers: list[tuple[str, Any]] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.answers.append((text, reply_markup))

    async def edit_text(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.answers.append((text, reply_markup))


@dataclass
class _FakeCb:
    from_user: _FakeUser
    message: _FakeMsg = field(default_factory=_FakeMsg)
    answered: list[str] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append(text)


async def _mkctx() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=8001,
        name="M",
        timezone="Asia/Yerevan",
        work_hours={
            "mon": [["10:00", "19:00"]],
            "tue": [["10:00", "19:00"]],
            "wed": [["10:00", "19:00"]],
            "thu": [["10:00", "19:00"]],
            "fri": [["10:00", "19:00"]],
            "sat": [["10:00", "16:00"]],
        },
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499010001")
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add_all([client, svc])
    await session.flush()
    await session.commit()
    return master, client, svc


@pytest.mark.asyncio
async def test_cmd_today_sends_day_schedule(session: AsyncSession) -> None:
    master, *_ = await _seed(session)
    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))

    await cmd_today(message=msg, state=state, session=session, master=master)
    assert msg.answers
    text, kb = msg.answers[0]
    assert "📅" in text
    assert kb is not None


@pytest.mark.asyncio
async def test_cmd_tomorrow_sends_day_schedule(session: AsyncSession) -> None:
    master, *_ = await _seed(session)
    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))

    await cmd_tomorrow(message=msg, state=state, session=session, master=master)
    assert msg.answers


@pytest.mark.asyncio
async def test_cb_day_nav_today_rerenders(session: AsyncSession) -> None:
    master, *_ = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_day_nav(
        callback=cb,  # type: ignore[arg-type]
        callback_data=DayNavCallback(action="today"),
        state=state,
        session=session,
        master=master,
    )
    assert cb.answered


@pytest.mark.asyncio
async def test_safe_edit_swallows_message_not_modified() -> None:
    class _RaisingMsg:
        async def edit_text(self, text: str, reply_markup: Any = None, **_: Any) -> None:
            raise TelegramBadRequest(
                method=MagicMock(),
                message="Bad Request: message is not modified",
            )

    # Should not raise.
    await safe_edit(_RaisingMsg(), "hello", MagicMock())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_safe_edit_reraises_other_telegram_errors() -> None:
    class _RaisingMsg:
        async def edit_text(self, text: str, reply_markup: Any = None, **_: Any) -> None:
            raise TelegramBadRequest(
                method=MagicMock(),
                message="Bad Request: chat not found",
            )

    with pytest.raises(TelegramBadRequest):
        await safe_edit(_RaisingMsg(), "hello", MagicMock())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_mark_past_button_present_for_past_confirmed(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    # Seed a confirmed appointment anchored to today in master's timezone so
    # the `today` view picks it up regardless of when the test runs (including
    # near-midnight edge cases in the master's local day).
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(master.timezone)
    today_local = datetime.now(UTC).astimezone(tz).date()
    local_start = datetime(today_local.year, today_local.month, today_local.day, 0, 0, tzinfo=tz)
    past_start = local_start.astimezone(UTC)
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=svc.id,
        start_at=past_start,
        end_at=past_start + timedelta(minutes=1),
        status="confirmed",
        source="master_manual",
        confirmed_at=past_start - timedelta(days=1),
    )
    session.add(appt)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))
    await cmd_today(message=msg, state=state, session=session, master=master)
    _, kb = msg.answers[0]
    packed = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
    assert any(p.startswith("mpa:") for p in packed)
