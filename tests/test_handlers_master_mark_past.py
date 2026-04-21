from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.mark_past import MarkPastCallback
from src.db.models import Appointment, Client, Master, Service
from src.handlers.master.mark_past import cb_mark_past
from src.strings import strings


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
    message: _FakeMsg | None = field(default_factory=_FakeMsg)
    answered: list[tuple[str, bool]] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append((text, show_alert))


async def _mkctx() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=9001,
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


async def _seed_past_confirmed(
    session: AsyncSession, master: Master, client: Client, svc: Service
) -> Appointment:
    now = datetime.now(UTC)
    past_start = now - timedelta(hours=3)
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=svc.id,
        start_at=past_start,
        end_at=past_start + timedelta(minutes=60),
        status="confirmed",
        source="master_manual",
        confirmed_at=past_start - timedelta(days=1),
    )
    session.add(appt)
    await session.flush()
    await session.commit()
    return appt


async def _reload(session: AsyncSession, appt_id: UUID) -> Appointment:
    res = await session.execute(select(Appointment).where(Appointment.id == appt_id))
    row = res.scalar_one()
    await session.refresh(row)
    return row


@pytest.mark.asyncio
async def test_cb_mark_past_present_transitions_to_completed(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    appt = await _seed_past_confirmed(session, master, client, svc)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_mark_past(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MarkPastCallback(action="present", appointment_id=appt.id),
        state=state,
        session=session,
        master=master,
    )

    reloaded = await _reload(session, appt.id)
    assert reloaded.status == "completed"
    assert cb.answered
    text, _ = cb.answered[0]
    assert text == strings.MARK_PAST_OK_COMPLETED


@pytest.mark.asyncio
async def test_cb_mark_past_no_show_transitions(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    appt = await _seed_past_confirmed(session, master, client, svc)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_mark_past(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MarkPastCallback(action="no_show", appointment_id=appt.id),
        state=state,
        session=session,
        master=master,
    )

    reloaded = await _reload(session, appt.id)
    assert reloaded.status == "no_show"
    assert cb.answered
    text, _ = cb.answered[0]
    assert text == strings.MARK_PAST_OK_NO_SHOW


@pytest.mark.asyncio
async def test_cb_mark_past_unknown_shows_alert(session: AsyncSession) -> None:
    master, *_ = await _seed(session)
    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_mark_past(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MarkPastCallback(action="present", appointment_id=uuid4()),
        state=state,
        session=session,
        master=master,
    )

    assert cb.answered
    text, alert = cb.answered[0]
    assert text == strings.MARK_PAST_NOT_AVAILABLE
    assert alert is True


@pytest.mark.asyncio
async def test_cb_mark_past_invalid_state_not_ended_shows_alert(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    # Seed future confirmed — not ended yet.
    future_start = datetime.now(UTC) + timedelta(hours=3)
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=svc.id,
        start_at=future_start,
        end_at=future_start + timedelta(minutes=60),
        status="confirmed",
        source="master_manual",
        confirmed_at=datetime.now(UTC),
    )
    session.add(appt)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_mark_past(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MarkPastCallback(action="present", appointment_id=appt.id),
        state=state,
        session=session,
        master=master,
    )

    assert cb.answered
    text, alert = cb.answered[0]
    assert text == strings.MARK_PAST_NOT_ENDED
    assert alert is True


@pytest.mark.asyncio
async def test_cb_mark_past_invalid_state_already_closed_shows_alert(session: AsyncSession) -> None:
    master, client, svc = await _seed(session)
    now = datetime.now(UTC)
    past_start = now - timedelta(hours=3)
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=svc.id,
        start_at=past_start,
        end_at=past_start + timedelta(minutes=60),
        status="completed",
        source="master_manual",
        confirmed_at=past_start - timedelta(days=1),
    )
    session.add(appt)
    await session.flush()
    await session.commit()

    state = await _mkctx()
    cb = _FakeCb(from_user=_FakeUser(id=master.tg_id))

    await cb_mark_past(
        callback=cb,  # type: ignore[arg-type]
        callback_data=MarkPastCallback(action="present", appointment_id=appt.id),
        state=state,
        session=session,
        master=master,
    )

    assert cb.answered
    text, alert = cb.answered[0]
    assert text == strings.MARK_PAST_ALREADY_CLOSED
    assert alert is True
