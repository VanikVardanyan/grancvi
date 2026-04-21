from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.schedule import DayPickCallback
from src.db.models import Appointment, Client, Master, Service
from src.handlers.master.week import cb_day_pick, cmd_week, render_week


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMsg:
    from_user: _FakeUser | None = None
    answers: list[tuple[str, Any]] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
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


async def _seed(session: AsyncSession) -> Master:
    master = Master(
        tg_id=8201,
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
    await session.commit()
    return master


@pytest.mark.asyncio
async def test_cmd_week_sends_snapshot(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))
    await cmd_week(message=msg, state=state, session=session, master=master)  # type: ignore[arg-type]
    assert msg.answers
    text, kb = msg.answers[0]
    assert "🗓" in text
    packed = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
    dpk = [p for p in packed if p.startswith("dpk:")]
    assert len(dpk) == 7


@pytest.mark.asyncio
async def test_render_week_reflects_load(session: AsyncSession) -> None:
    master = await _seed(session)
    tz = ZoneInfo("Asia/Yerevan")
    tomorrow = (datetime.now(UTC).astimezone(tz) + timedelta(days=1)).date()
    start_local = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 11, tzinfo=tz)
    start = start_local.astimezone(UTC)
    client = Client(master_id=master.id, name="C", phone="+37499030001")
    svc = Service(master_id=master.id, name="S", duration_min=60)
    session.add_all([client, svc])
    await session.flush()
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=svc.id,
        start_at=start,
        end_at=start + timedelta(minutes=60),
        status="confirmed",
        source="master_manual",
    )
    session.add(appt)
    await session.flush()
    await session.commit()

    text, _ = await render_week(session=session, master=master)
    assert "1 зап" in text


@pytest.mark.asyncio
async def test_cb_day_pick_sends_day_schedule(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_day_pick(
        callback=cb,  # type: ignore[arg-type]
        callback_data=DayPickCallback(ymd="2026-04-24"),
        state=state,
        session=session,
        master=master,
    )
    assert cb.message.answers
