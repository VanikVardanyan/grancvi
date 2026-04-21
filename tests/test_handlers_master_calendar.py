from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.master_calendar import MasterCalendarCallback
from src.db.models import Master
from src.handlers.master.calendar import cb_master_calendar, cmd_calendar, render_calendar


@dataclass
class _FakeUser:
    id: int


class _FakeMsg(Message):
    """Subclass of aiogram Message so isinstance(..., Message) passes.

    Tracks answer() calls in `answers` and edit_text() calls in `edits`.
    """

    @classmethod
    def make(cls) -> _FakeMsg:
        inst = cls.model_construct(
            message_id=1,
            chat=Chat.model_construct(id=1, type="private"),
            date=datetime.now(UTC),
        )
        object.__setattr__(inst, "answers", [])
        object.__setattr__(inst, "edits", [])
        return inst

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> Any:  # type: ignore[override]
        self.answers.append((text, reply_markup))  # type: ignore[attr-defined]
        return None

    async def edit_text(self, text: str, reply_markup: Any = None, **_: Any) -> Any:  # type: ignore[override]
        self.edits.append((text, reply_markup))  # type: ignore[attr-defined]
        return None


@dataclass
class _FakeCb:
    from_user: _FakeUser
    message: _FakeMsg = field(default_factory=lambda: _FakeMsg.make())
    answered: list[str] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append(text)


async def _mkctx() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed(session: AsyncSession) -> Master:
    master = Master(
        tg_id=8301,
        name="M",
        timezone="Asia/Yerevan",
        work_hours={"mon": [["10:00", "19:00"]]},
    )
    session.add(master)
    await session.flush()
    await session.commit()
    return master


@pytest.mark.asyncio
async def test_cmd_calendar_renders_current_month(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    msg = _FakeMsg.make()
    await cmd_calendar(message=msg, state=state, session=session, master=master)  # type: ignore[arg-type]
    assert msg.answers


@pytest.mark.asyncio
async def test_cb_master_calendar_nav_to_prior_month(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_master_calendar(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MasterCalendarCallback(action="nav", year=2026, month=3, day=0),
        state=state,
        session=session,
        master=master,
    )
    # Nav edits the existing message in place.
    assert cb.message.edits
    assert not cb.message.answers


@pytest.mark.asyncio
async def test_cb_master_calendar_pick_sends_day(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_master_calendar(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MasterCalendarCallback(action="pick", year=2026, month=4, day=20),
        state=state,
        session=session,
        master=master,
    )
    # Deviation 2: pick edits in place, not sends a new message.
    assert cb.message.edits
    assert not cb.message.answers


@pytest.mark.asyncio
async def test_cb_master_calendar_noop_just_answers(session: AsyncSession) -> None:
    master = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_master_calendar(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MasterCalendarCallback(action="noop", year=2026, month=4, day=0),
        state=state,
        session=session,
        master=master,
    )
    assert cb.answered
    assert not cb.message.edits
    assert not cb.message.answers


@pytest.mark.asyncio
async def test_render_calendar_current_month_default(session: AsyncSession) -> None:
    master = await _seed(session)
    text, kb = await render_calendar(session=session, master=master, month=None)
    assert text
    assert kb is not None


@pytest.mark.asyncio
async def test_render_calendar_past_month(session: AsyncSession) -> None:
    master = await _seed(session)
    text, kb = await render_calendar(session=session, master=master, month=date(2025, 1, 1))
    assert text
    # Past-month cells should still include 'pick' actions (allow_past=True).
    packed = [btn.callback_data for row in kb.inline_keyboard for btn in row if btn.callback_data]
    assert any(p.startswith("mca:pick") for p in packed)
