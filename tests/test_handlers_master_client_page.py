from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.client_page import (
    ClientAddApptCallback,
    ClientNotesEditCallback,
    ClientPickCallback,
)
from src.db.models import Appointment, Client, Master, Service
from src.fsm.master_add import MasterAdd
from src.fsm.master_view import MasterView
from src.handlers.master.client_page import (
    _render_client_page,
    cb_add_appt,
    cb_edit_notes,
    cb_pick_client,
    cmd_client,
    msg_notes_edit,
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
    answered: list[tuple[str, bool]] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append((text, show_alert))


async def _mkctx() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed_master(session: AsyncSession) -> Master:
    m = Master(tg_id=7700, name="M", timezone="Asia/Yerevan")
    session.add(m)
    await session.flush()
    await session.commit()
    return m


async def _seed_client(
    session: AsyncSession, master: Master, *, name: str = "Анна", phone: str = "+37499111111"
) -> Client:
    c = Client(master_id=master.id, name=name, phone=phone)
    session.add(c)
    await session.flush()
    await session.commit()
    return c


@pytest.mark.asyncio
async def test_cmd_client_enters_search_state(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id))
    await cmd_client(message=msg, state=state, session=session, master=master)  # type: ignore[arg-type]
    assert await state.get_state() == MasterView.SearchingClient.state
    assert msg.answers


@pytest.mark.asyncio
async def test_msg_search_too_short_stays(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterView.SearchingClient)
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="a")
    await msg_search_query(message=msg, state=state, session=session, master=master)  # type: ignore[arg-type]
    assert await state.get_state() == MasterView.SearchingClient.state
    assert msg.answers


@pytest.mark.asyncio
async def test_msg_search_one_result_opens_page(session: AsyncSession) -> None:
    master = await _seed_master(session)
    client = await _seed_client(session, master, name="Анна", phone="+37499111111")
    state = await _mkctx()
    await state.set_state(MasterView.SearchingClient)
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="Анна")
    await msg_search_query(message=msg, state=state, session=session, master=master)  # type: ignore[arg-type]
    # Single match → state cleared, page rendered
    assert await state.get_state() is None
    assert msg.answers
    text, _ = msg.answers[0]
    assert client.name in text


@pytest.mark.asyncio
async def test_msg_search_many_results_shows_picker(session: AsyncSession) -> None:
    master = await _seed_master(session)
    await _seed_client(session, master, name="Анна Иванова", phone="+37499111111")
    await _seed_client(session, master, name="Анна Петрова", phone="+37499222222")
    state = await _mkctx()
    await state.set_state(MasterView.SearchingClient)
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="Анна")
    await msg_search_query(message=msg, state=state, session=session, master=master)  # type: ignore[arg-type]
    # Still in search state; user picks via inline keyboard
    assert await state.get_state() == MasterView.SearchingClient.state
    assert msg.answers
    _, kb = msg.answers[0]
    assert kb is not None


@pytest.mark.asyncio
async def test_msg_search_empty_results_reprompts(session: AsyncSession) -> None:
    master = await _seed_master(session)
    state = await _mkctx()
    await state.set_state(MasterView.SearchingClient)
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="Неизвестный")
    await msg_search_query(message=msg, state=state, session=session, master=master)  # type: ignore[arg-type]
    assert await state.get_state() == MasterView.SearchingClient.state
    assert msg.answers


@pytest.mark.asyncio
async def test_cb_pick_client_opens_page(session: AsyncSession) -> None:
    master = await _seed_master(session)
    client = await _seed_client(session, master)
    state = await _mkctx()
    await state.set_state(MasterView.SearchingClient)
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_pick_client(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientPickCallback(client_id=client.id),
        state=state,
        session=session,
        master=master,
    )
    # State cleared and page sent as new message
    assert await state.get_state() is None
    assert cb.message.answers
    text, _ = cb.message.answers[0]
    assert client.name in text


@pytest.mark.asyncio
async def test_cb_pick_unknown_client_answers_not_found(session: AsyncSession) -> None:
    master = await _seed_master(session)
    # Client belonging to a DIFFERENT master
    other = Master(tg_id=7701, name="Other", timezone="Asia/Yerevan")
    session.add(other)
    await session.flush()
    foreign = Client(master_id=other.id, name="X", phone="+37499333333")
    session.add(foreign)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_pick_client(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientPickCallback(client_id=foreign.id),
        state=state,
        session=session,
        master=master,
    )
    # Not-found alert; no page rendered
    assert cb.answered
    assert any(show_alert for _, show_alert in cb.answered)
    assert not cb.message.answers


@pytest.mark.asyncio
async def test_cb_edit_notes_enters_editing_state(session: AsyncSession) -> None:
    master = await _seed_master(session)
    client = await _seed_client(session, master)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_edit_notes(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientNotesEditCallback(client_id=client.id),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterView.EditingNotes.state
    data = await state.get_data()
    assert data["client_id"] == str(client.id)
    assert cb.message.answers


@pytest.mark.asyncio
async def test_msg_notes_edit_saves_value(session: AsyncSession) -> None:
    master = await _seed_master(session)
    client = await _seed_client(session, master)
    state = await _mkctx()
    await state.set_state(MasterView.EditingNotes)
    await state.update_data(client_id=str(client.id))
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="Аллергия на лидокаин")
    await msg_notes_edit(message=msg, state=state, session=session, master=master)  # type: ignore[arg-type]
    assert await state.get_state() is None
    await session.refresh(client)
    assert client.notes == "Аллергия на лидокаин"
    assert msg.answers


@pytest.mark.asyncio
async def test_msg_notes_edit_dash_clears_value(session: AsyncSession) -> None:
    master = await _seed_master(session)
    client = await _seed_client(session, master)
    client.notes = "старое"
    await session.flush()
    await session.commit()

    state = await _mkctx()
    await state.set_state(MasterView.EditingNotes)
    await state.update_data(client_id=str(client.id))
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text="-")
    await msg_notes_edit(message=msg, state=state, session=session, master=master)  # type: ignore[arg-type]
    await session.refresh(client)
    assert client.notes is None


@pytest.mark.asyncio
async def test_msg_notes_edit_caps_at_500_chars(session: AsyncSession) -> None:
    master = await _seed_master(session)
    client = await _seed_client(session, master)
    state = await _mkctx()
    await state.set_state(MasterView.EditingNotes)
    await state.update_data(client_id=str(client.id))
    long_text = "x" * 700
    msg = _FakeMsg(from_user=_FakeUser(id=master.tg_id), text=long_text)
    await msg_notes_edit(message=msg, state=state, session=session, master=master)  # type: ignore[arg-type]
    await session.refresh(client)
    assert client.notes is not None
    assert len(client.notes) == 500


@pytest.mark.asyncio
async def test_cb_add_appt_bridges_to_picking_service(session: AsyncSession) -> None:
    master = await _seed_master(session)
    client = await _seed_client(session, master)
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(svc)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_add_appt(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientAddApptCallback(client_id=client.id),
        state=state,
        session=session,
        master=master,
    )
    assert await state.get_state() == MasterAdd.PickingService.state
    data = await state.get_data()
    assert data["client_id"] == str(client.id)
    assert cb.message.answers


@pytest.mark.asyncio
async def test_client_page_shows_more_suffix_when_history_exceeds_limit(
    session: AsyncSession,
) -> None:
    master = await _seed_master(session)
    client = await _seed_client(session, master)
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(svc)
    await session.flush()

    now = datetime.now(UTC)
    for i in range(22):
        session.add(
            Appointment(
                master_id=master.id,
                client_id=client.id,
                service_id=svc.id,
                start_at=now - timedelta(days=i + 1),
                end_at=now - timedelta(days=i + 1) + timedelta(minutes=60),
                status="completed",
                source="master_manual",
                confirmed_at=now - timedelta(days=i + 2),
            )
        )
    await session.flush()
    await session.commit()

    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))
    await cb_pick_client(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ClientPickCallback(client_id=client.id),
        state=state,
        session=session,
        master=master,
    )
    text, _ = cb.message.answers[0]
    from src.strings import strings as _s

    expected_tail = _s.CLIENT_PAGE_HISTORY_MORE.format(n=2)
    assert expected_tail in text


@pytest.mark.asyncio
async def test_client_page_includes_recent_history(session: AsyncSession) -> None:
    master = Master(
        tg_id=7800,
        name="M",
        timezone="Asia/Yerevan",
        work_hours={"mon": [["10:00", "19:00"]]},
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499111111")
    session.add(client)
    svc = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(svc)
    await session.flush()

    past = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=svc.id,
        start_at=past,
        end_at=past + timedelta(minutes=60),
        status="completed",
        source="master_manual",
    )
    session.add(appt)
    await session.flush()
    await session.commit()

    text, kb = await _render_client_page(session=session, master=master, client=client)
    assert client.name in text
    assert "Стрижка" in text
    assert kb is not None
