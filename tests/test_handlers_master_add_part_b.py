from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.master_add import CustomTimeCallback, SkipCommentCallback
from src.callback_data.slots import SlotCallback
from src.db.models import Client, Master, Service
from src.fsm.master_add import MasterAdd
from src.handlers.master.add_manual import (
    cb_confirm_cancel,
    cb_confirm_save,
    cb_custom_time,
    cb_pick_slot,
    cb_skip_comment,
    cmd_cancel_any,
    msg_comment,
    msg_custom_time,
)


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMsg:
    from_user: _FakeUser | None = None
    text: str | None = None
    answers: list[tuple[str, Any]] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.answers.append((text, reply_markup))


@dataclass
class _FakeCb:
    from_user: _FakeUser
    message: _FakeMsg = field(default_factory=_FakeMsg)
    answered: list[tuple[str, bool]] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append((text, show_alert))


async def _mkctx() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=6200,
        name="M",
        timezone="Asia/Yerevan",
        work_hours={
            "mon": [["10:00", "19:00"]],
            "tue": [["10:00", "19:00"]],
            "wed": [["10:00", "19:00"]],
            "thu": [["10:00", "19:00"]],
            "fri": [["10:00", "19:00"]],
            "sat": [["10:00", "19:00"]],
            "sun": [["10:00", "19:00"]],
        },
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499200200", tg_id=None)
    session.add(client)
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(svc)
    await session.flush()
    await session.commit()
    return master, client, svc


@pytest.mark.asyncio
async def test_cb_pick_slot_advances_to_comment(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.PickingSlot)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        date=date(2026, 5, 4).isoformat(),
    )
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_pick_slot(
        callback=cb,  # type: ignore[arg-type]
        callback_data=SlotCallback(hour=11, minute=0),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.EnteringComment.state
    data = await state.get_data()
    assert "start_at" in data


@pytest.mark.asyncio
async def test_cb_custom_time_enters_custom_state(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.PickingSlot)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        date=date(2026, 5, 4).isoformat(),
    )
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_custom_time(
        callback=cb,  # type: ignore[arg-type]
        callback_data=CustomTimeCallback(),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.EnteringCustomTime.state


@pytest.mark.asyncio
async def test_msg_custom_time_bad_format_stays(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.EnteringCustomTime)
    await state.update_data(date=date(2026, 5, 4).isoformat())
    msg = _FakeMsg(text="завтра вечером")
    await msg_custom_time(message=msg, state=state, master=master)
    assert await state.get_state() == MasterAdd.EnteringCustomTime.state


@pytest.mark.asyncio
async def test_msg_custom_time_past_rejected(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.EnteringCustomTime)
    await state.update_data(date=date(2020, 1, 1).isoformat())
    msg = _FakeMsg(text="10:00")
    await msg_custom_time(message=msg, state=state, master=master)
    assert await state.get_state() == MasterAdd.EnteringCustomTime.state


@pytest.mark.asyncio
async def test_msg_custom_time_ok_advances(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.EnteringCustomTime)
    # Pick a date in 2030 so it's always in the future for test determinism.
    await state.update_data(date=date(2030, 6, 1).isoformat())
    msg = _FakeMsg(text="25.06 14:30")
    await msg_custom_time(message=msg, state=state, master=master)
    assert await state.get_state() == MasterAdd.EnteringComment.state


@pytest.mark.asyncio
async def test_msg_comment_advances_to_confirming(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.EnteringComment)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        start_at=datetime(2030, 6, 25, 10, 30, tzinfo=UTC).isoformat(),
    )
    msg = _FakeMsg(text="Принести шампунь")
    await msg_comment(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterAdd.Confirming.state
    assert (await state.get_data())["comment"] == "Принести шампунь"


@pytest.mark.asyncio
async def test_cb_skip_comment_advances_to_confirming(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.EnteringComment)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        start_at=datetime(2030, 6, 25, 10, 30, tzinfo=UTC).isoformat(),
    )
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_skip_comment(
        callback=cb,  # type: ignore[arg-type]
        callback_data=SkipCommentCallback(),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.Confirming.state
    assert (await state.get_data())["comment"] is None


@pytest.mark.asyncio
async def test_cb_confirm_save_creates_appointment_clears_state(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.Confirming)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        start_at=datetime(2030, 6, 25, 10, 30, tzinfo=UTC).isoformat(),
        comment=None,
    )
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    bot = AsyncMock()
    await cb_confirm_save(
        callback=cb,  # type: ignore[arg-type]
        state=state,
        session=session,
        master=master,
        bot=bot,
    )
    assert await state.get_state() is None  # cleared
    # client has no tg_id -> no notification
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_cb_confirm_save_notifies_client_when_tg_present(session: AsyncSession) -> None:
    master = Master(
        tg_id=6201,
        name="M",
        timezone="Asia/Yerevan",
        work_hours={"mon": [["10:00", "19:00"]]},
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Борис", phone="+37499300300", tg_id=77777)
    session.add(client)
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(svc)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterAdd.Confirming)
    await state.update_data(
        client_id=str(client.id),
        service_id=str(svc.id),
        start_at=datetime(2030, 6, 25, 10, 30, tzinfo=UTC).isoformat(),
        comment=None,
    )
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    bot = AsyncMock()
    await cb_confirm_save(
        callback=cb,  # type: ignore[arg-type]
        state=state,
        session=session,
        master=master,
        bot=bot,
    )
    bot.send_message.assert_awaited_once()
    _, kwargs = bot.send_message.call_args
    assert kwargs["chat_id"] == 77777


@pytest.mark.asyncio
async def test_cb_confirm_cancel_clears_state(session: AsyncSession) -> None:
    master, _, _ = await _seed(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.Confirming)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_confirm_cancel(callback=cb, state=state)  # type: ignore[arg-type]
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_cmd_cancel_any_clears_state(session: AsyncSession) -> None:
    state = await _mkctx()
    await state.set_state(MasterAdd.PickingService)
    msg = _FakeMsg()
    await cmd_cancel_any(message=msg, state=state)
    assert await state.get_state() is None
