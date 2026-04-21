from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.client_services import ClientServicePick
from src.callback_data.master_add import PhoneDupCallback, RecentClientCallback
from src.db.models import Client, Master, Service
from src.fsm.master_add import MasterAdd
from src.handlers.master.add_manual import (
    cb_phone_dup,
    cb_pick_recent,
    cb_pick_service,
    cmd_add,
    msg_new_client_name,
    msg_new_client_phone,
    msg_search_query,
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
    answered: list[str] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append(text)


async def _mkctx() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed_master(session: AsyncSession) -> Master:
    m = Master(tg_id=5500, name="M", timezone="Asia/Yerevan")
    session.add(m)
    await session.flush()
    await session.commit()
    return m


@pytest.mark.asyncio
async def test_cmd_add_empty_state_shows_no_recent_hint(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))
    await cmd_add(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterAdd.PickingClient.state
    # No clients yet — hint text + keyboard with only control row
    assert msg.answers


@pytest.mark.asyncio
async def test_cb_pick_recent_new_transitions_to_name(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.PickingClient)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_pick_recent(
        callback=cb,  # type: ignore[arg-type]
        callback_data=RecentClientCallback(client_id="new"),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.NewClientName.state


@pytest.mark.asyncio
async def test_cb_pick_recent_search_transitions_to_search(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.PickingClient)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_pick_recent(
        callback=cb,  # type: ignore[arg-type]
        callback_data=RecentClientCallback(client_id="search"),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.SearchingClient.state


@pytest.mark.asyncio
async def test_cb_pick_recent_existing_goes_to_service_pick(session: AsyncSession) -> None:
    master = await _seed_master(session)
    client = Client(master_id=master.id, name="Анна", phone="+37499111111")
    session.add(client)
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(svc)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterAdd.PickingClient)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_pick_recent(
        callback=cb,  # type: ignore[arg-type]
        callback_data=RecentClientCallback(client_id=str(client.id)),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.PickingService.state
    assert (await state.get_data())["client_id"] == str(client.id)


@pytest.mark.asyncio
async def test_msg_search_below_min_length_keeps_state(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.SearchingClient)
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="a")
    await msg_search_query(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterAdd.SearchingClient.state


@pytest.mark.asyncio
async def test_msg_new_client_name_too_short_keeps_state(session: AsyncSession) -> None:
    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientName)
    msg = _FakeMsg(text="A")
    await msg_new_client_name(message=msg, state=state)
    assert await state.get_state() == MasterAdd.NewClientName.state


@pytest.mark.asyncio
async def test_msg_new_client_name_ok_advances(session: AsyncSession) -> None:
    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientName)
    msg = _FakeMsg(text="Борис")
    await msg_new_client_name(message=msg, state=state)
    assert await state.get_state() == MasterAdd.NewClientPhone.state
    assert (await state.get_data())["pending_name"] == "Борис"


@pytest.mark.asyncio
async def test_msg_new_client_phone_fresh_creates_and_advances(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientPhone)
    await state.update_data(pending_name="Борис")
    msg = _FakeMsg(text="+374991122333")  # correct length example below
    # Fix: +37499112233 (8 national digits)
    msg.text = "+37499112233"
    await msg_new_client_phone(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterAdd.PickingService.state
    data = await state.get_data()
    assert "client_id" in data


@pytest.mark.asyncio
async def test_msg_new_client_phone_dup_waits_for_decision(session: AsyncSession) -> None:
    master = await _seed_master(session)
    existing = Client(master_id=master.id, name="Анна", phone="+37499500500")
    session.add(existing)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientPhone)
    await state.update_data(pending_name="Аня")
    msg = _FakeMsg(text="+37499500500")
    await msg_new_client_phone(message=msg, state=state, session=session, master=master)
    assert await state.get_state() == MasterAdd.NewClientPhone.state
    assert (await state.get_data())["pending_phone"] == "+37499500500"


@pytest.mark.asyncio
async def test_cb_phone_dup_use_advances(session: AsyncSession) -> None:
    master = await _seed_master(session)
    existing = Client(master_id=master.id, name="Анна", phone="+37499500500")
    session.add(existing)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientPhone)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_phone_dup(
        callback=cb,  # type: ignore[arg-type]
        callback_data=PhoneDupCallback(action="use", client_id=existing.id),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.PickingService.state
    assert (await state.get_data())["client_id"] == str(existing.id)


@pytest.mark.asyncio
async def test_cb_phone_dup_retry_prompts_again(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterAdd.NewClientPhone)
    await state.update_data(pending_name="Аня", pending_phone="+37499500500")
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_phone_dup(
        callback=cb,  # type: ignore[arg-type]
        callback_data=PhoneDupCallback(action="retry", client_id=uuid4()),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.NewClientPhone.state
    data = await state.get_data()
    assert "pending_phone" not in data


@pytest.mark.asyncio
async def test_cb_pick_service_advances_to_date(session: AsyncSession) -> None:
    master = Master(
        tg_id=5600,
        name="M",
        timezone="Asia/Yerevan",
        work_hours={"mon": [["10:00", "19:00"]]},
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499000700")
    session.add(client)
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(svc)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterAdd.PickingService)
    await state.update_data(client_id=str(client.id))
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_pick_service(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientServicePick(service_id=svc.id),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.PickingDate.state
    assert (await state.get_data())["service_id"] == str(svc.id)
