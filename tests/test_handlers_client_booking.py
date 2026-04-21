# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.calendar import CalendarCallback
from src.callback_data.client_services import ClientServicePick
from src.callback_data.slots import SlotCallback
from src.db.models import Client, Master, Service
from src.fsm.client_booking import ClientBooking
from src.handlers.client.booking import (
    handle_date_pick,
    handle_service_pick,
)
from src.handlers.client.start import handle_start


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
class _FakeCallback:
    data: str
    from_user: _FakeUser
    message: _FakeMsg
    answered: list[Any] = field(default_factory=list)

    async def answer(self, *args: Any, **kwargs: Any) -> None:
        self.answered.append((args, kwargs))


def _make_fsm(tg_id: int) -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(),
        key=StorageKey(bot_id=1, chat_id=tg_id, user_id=tg_id),
    )


@pytest.mark.asyncio
async def test_start_no_master_replies_with_stub(session: AsyncSession) -> None:
    msg = _FakeMsg(from_user=_FakeUser(id=123))
    state = _make_fsm(123)

    await handle_start(msg, master=None, state=state, session=session)

    assert msg.answers
    text, _ = msg.answers[0]
    assert "не настроен" in text


@pytest.mark.asyncio
async def test_start_with_master_via_singleton_shows_services(
    session: AsyncSession,
) -> None:
    master = Master(tg_id=7777, name="Мастер")
    session.add(master)
    await session.flush()
    session.add(Service(master_id=master.id, name="Стрижка", duration_min=60))
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=42))  # tg_id != master.tg_id → client path
    state = _make_fsm(42)

    await handle_start(msg, master=None, state=state, session=session)

    assert msg.answers
    text, kb = msg.answers[-1]
    assert "услугу" in text.lower()
    assert kb is not None  # services_pick_kb with one row
    current = await state.get_state()
    assert current == ClientBooking.ChoosingService.state


@pytest.mark.asyncio
async def test_start_with_empty_services_shows_no_services(
    session: AsyncSession,
) -> None:
    master = Master(tg_id=7778, name="Мастер")
    session.add(master)
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=43))
    state = _make_fsm(43)

    await handle_start(msg, master=None, state=state, session=session)

    text, _ = msg.answers[-1]
    assert "услуг" in text.lower()


@pytest.mark.asyncio
async def test_service_pick_saves_id_and_renders_calendar(
    session: AsyncSession,
) -> None:
    master = Master(
        tg_id=9000,
        name="М",
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        slot_step_min=60,
        timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=55))
    cb = _FakeCallback(
        data=ClientServicePick(service_id=service.id).pack(),
        from_user=_FakeUser(id=55),
        message=msg,
    )
    state = _make_fsm(55)
    await state.set_state(ClientBooking.ChoosingService)

    cb_data = ClientServicePick(service_id=service.id)
    await handle_service_pick(cb, callback_data=cb_data, state=state, session=session)

    assert await state.get_state() == ClientBooking.ChoosingDate.state
    data = await state.get_data()
    assert data["service_id"] == str(service.id)
    # Calendar rendered in msg.answers
    assert msg.answers
    _, kb = msg.answers[-1]
    assert kb is not None


@pytest.mark.asyncio
async def test_date_pick_renders_slots_or_no_slots(session: AsyncSession) -> None:
    master = Master(
        tg_id=9001,
        name="М",
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        slot_step_min=60,
        timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=66))
    # Monday 2026-05-04 — work day; handler will compute free slots.
    cb = _FakeCallback(
        data=CalendarCallback(action="pick", year=2026, month=5, day=4).pack(),
        from_user=_FakeUser(id=66),
        message=msg,
    )
    state = _make_fsm(66)
    await state.set_state(ClientBooking.ChoosingDate)
    await state.update_data(service_id=str(service.id))

    cb_data = CalendarCallback(action="pick", year=2026, month=5, day=4)
    await handle_date_pick(cb, callback_data=cb_data, state=state, session=session)

    assert await state.get_state() == ClientBooking.ChoosingTime.state
    data = await state.get_data()
    assert data["date"] == "2026-05-04"


@pytest.mark.asyncio
async def test_time_pick_saves_start_and_asks_name(session: AsyncSession) -> None:
    master = Master(
        tg_id=9100,
        name="М",
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        slot_step_min=60,
        timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    from src.handlers.client.booking import handle_time_pick

    msg = _FakeMsg(from_user=_FakeUser(id=77))
    cb = _FakeCallback(
        data=SlotCallback(hour=14, minute=0).pack(),
        from_user=_FakeUser(id=77),
        message=msg,
    )
    state = _make_fsm(77)
    await state.set_state(ClientBooking.ChoosingTime)
    await state.update_data(
        master_id=str(master.id),
        service_id=str(service.id),
        date="2026-05-04",
    )

    cb_data = SlotCallback(hour=14, minute=0)
    await handle_time_pick(cb, callback_data=cb_data, state=state, session=session)

    assert await state.get_state() == ClientBooking.EnteringName.state
    data = await state.get_data()
    assert data["start_at"].startswith("2026-05-04T")
    assert msg.answers
    text, _ = msg.answers[-1]
    assert "зовут" in text.lower() or "имя" in text.lower()


@pytest.mark.asyncio
async def test_name_valid_moves_to_phone(session: AsyncSession) -> None:
    from src.handlers.client.booking import handle_name

    msg = _FakeMsg(from_user=_FakeUser(id=88))
    msg.text = "Анна"
    state = _make_fsm(88)
    await state.set_state(ClientBooking.EnteringName)

    await handle_name(msg, state=state)

    assert await state.get_state() == ClientBooking.EnteringPhone.state
    data = await state.get_data()
    assert data["name"] == "Анна"


@pytest.mark.asyncio
async def test_name_empty_retries_same_state(session: AsyncSession) -> None:
    from src.handlers.client.booking import handle_name

    msg = _FakeMsg(from_user=_FakeUser(id=89))
    msg.text = "   "
    state = _make_fsm(89)
    await state.set_state(ClientBooking.EnteringName)

    await handle_name(msg, state=state)

    assert await state.get_state() == ClientBooking.EnteringName.state
    assert msg.answers


@pytest.mark.asyncio
async def test_phone_invalid_retries(session: AsyncSession) -> None:
    from src.handlers.client.booking import handle_phone

    msg = _FakeMsg(from_user=_FakeUser(id=90))
    msg.text = "abc"
    state = _make_fsm(90)
    await state.set_state(ClientBooking.EnteringPhone)

    await handle_phone(msg, state=state, session=session)

    assert await state.get_state() == ClientBooking.EnteringPhone.state


@pytest.mark.asyncio
async def test_phone_valid_renders_confirm(session: AsyncSession) -> None:
    from src.handlers.client.booking import handle_phone

    master = Master(
        tg_id=9200,
        name="М",
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        slot_step_min=60,
        timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=91))
    msg.text = "+374 99 111 222"
    state = _make_fsm(91)
    await state.set_state(ClientBooking.EnteringPhone)
    await state.update_data(
        master_id=str(master.id),
        service_id=str(service.id),
        date="2026-05-04",
        start_at=datetime(2026, 5, 4, 10, 0, tzinfo=UTC).isoformat(),
        name="Аня",
    )

    await handle_phone(msg, state=state, session=session)

    assert await state.get_state() == ClientBooking.Confirming.state
    data = await state.get_data()
    assert data["phone"] == "+37499111222"
    assert msg.answers
    text, kb = msg.answers[-1]
    assert "Подтвердить" in text or "проверьте" in text.lower()
    assert kb is not None


@pytest.mark.asyncio
async def test_confirm_creates_pending_and_notifies_master(
    session: AsyncSession,
) -> None:
    from src.handlers.client.booking import handle_confirm

    master = Master(
        tg_id=9300,
        name="М",
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        slot_step_min=60,
        timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=92))
    cb = _FakeCallback(data="client_confirm", from_user=_FakeUser(id=92), message=msg)
    state = _make_fsm(92)
    await state.set_state(ClientBooking.Confirming)
    start_at = datetime(2026, 5, 4, 10, 0, tzinfo=UTC)
    await state.update_data(
        master_id=str(master.id),
        service_id=str(service.id),
        date="2026-05-04",
        start_at=start_at.isoformat(),
        name="Аня",
        phone="+37499111222",
    )

    bot = AsyncMock()
    await handle_confirm(cb, state=state, session=session, bot=bot)

    assert await state.get_state() is None
    bot.send_message.assert_awaited_once()
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == master.tg_id
    text, _ = msg.answers[-1]
    assert "отправлена" in text.lower() or "ждите" in text.lower()


@pytest.mark.asyncio
async def test_confirm_handles_slot_taken(session: AsyncSession) -> None:
    from src.handlers.client.booking import handle_confirm
    from src.repositories.appointments import AppointmentRepository

    master = Master(
        tg_id=9400,
        name="М",
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        slot_step_min=60,
        timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    existing_client = Client(master_id=master.id, name="Занимающий", phone="+37499000000")
    session.add(existing_client)
    await session.flush()
    repo = AppointmentRepository(session)
    start_at = datetime(2026, 5, 4, 6, 0, tzinfo=UTC)  # 10:00 Yerevan
    await repo.create(
        master_id=master.id,
        client_id=existing_client.id,
        service_id=service.id,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=60),
        status="confirmed",
        source="client_request",
    )
    await session.commit()

    msg = _FakeMsg(from_user=_FakeUser(id=93))
    cb = _FakeCallback(data="client_confirm", from_user=_FakeUser(id=93), message=msg)
    state = _make_fsm(93)
    await state.set_state(ClientBooking.Confirming)
    await state.update_data(
        master_id=str(master.id),
        service_id=str(service.id),
        date="2026-05-04",
        start_at=start_at.isoformat(),
        name="Аня",
        phone="+37499111222",
    )

    bot = AsyncMock()
    await handle_confirm(cb, state=state, session=session, bot=bot)

    assert await state.get_state() == ClientBooking.ChoosingTime.state
    bot.send_message.assert_not_awaited()
    texts = [t for t, _ in msg.answers]
    assert any("заняли" in t.lower() for t in texts)
