# ruff: noqa: RUF001
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.approval import ApprovalCallback
from src.db.models import Client, Master, Service
from src.repositories.appointments import AppointmentRepository


@dataclass
class _User:
    id: int


@dataclass
class _Msg:
    from_user: _User | None
    text: str = ""
    edits: list[tuple[str, Any]] = field(default_factory=list)
    answers: list[tuple[str, Any]] = field(default_factory=list)

    async def edit_text(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.text = text
        self.edits.append((text, reply_markup))

    async def answer(self, text: str, reply_markup: Any = None, **_: Any) -> None:
        self.answers.append((text, reply_markup))


@dataclass
class _Cb:
    from_user: _User
    message: _Msg
    data: str = ""
    answered: list[tuple[tuple[Any, ...], dict[str, Any]]] = field(default_factory=list)

    async def answer(self, *args: Any, **kwargs: Any) -> None:
        self.answered.append((args, kwargs))


async def _seed(session: AsyncSession) -> tuple[Master, Client, Service]:
    master = Master(
        tg_id=1111, name="М",
        work_hours={"mon": [["10:00", "19:00"]]}, breaks={},
        slot_step_min=60, timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Аня", phone="+37499000001", tg_id=2222)
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()
    return master, client, service


@pytest.mark.asyncio
async def test_confirm_happy_path_notifies_client(session: AsyncSession) -> None:
    from src.handlers.master.approve import cb_confirm

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="pending", source="client_request",
        decision_deadline=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
    )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id), text="🔔 Новая заявка…")
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="confirm", appointment_id=appt.id)

    await cb_confirm(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    await session.refresh(appt)
    assert appt.status == "confirmed"
    assert msg.edits
    edited_text, edited_kb = msg.edits[-1]
    assert "Подтверждено" in edited_text
    assert edited_kb is None
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == client.tg_id


@pytest.mark.asyncio
async def test_confirm_already_processed_gives_alert(session: AsyncSession) -> None:
    from src.handlers.master.approve import cb_confirm

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="confirmed",
        source="client_request",
        confirmed_at=datetime(2026, 5, 4, 6, 0, tzinfo=UTC),
    )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id))
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="confirm", appointment_id=appt.id)

    await cb_confirm(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    assert cb.answered
    _, kwargs = cb.answered[-1]
    assert kwargs.get("show_alert") is True
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_reject_updates_status_and_notifies_client(
    session: AsyncSession,
) -> None:
    from src.handlers.master.approve import cb_reject

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="pending", source="client_request",
        decision_deadline=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
    )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id), text="🔔 Новая заявка…")
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="reject", appointment_id=appt.id)

    await cb_reject(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    await session.refresh(appt)
    assert appt.status == "rejected"
    assert msg.edits
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == client.tg_id


@pytest.mark.asyncio
async def test_confirm_skips_client_notify_when_tg_id_missing(
    session: AsyncSession,
) -> None:
    from src.handlers.master.approve import cb_confirm

    master = Master(
        tg_id=1111, name="М",
        work_hours={"mon": [["10:00", "19:00"]]}, breaks={},
        slot_step_min=60, timezone="Asia/Yerevan",
    )
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Оффлайн", phone="+37499000099", tg_id=None)
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="pending", source="client_request",
        decision_deadline=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
    )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id))
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="confirm", appointment_id=appt.id)

    await cb_confirm(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    bot.send_message.assert_not_awaited()
    await session.refresh(appt)
    assert appt.status == "confirmed"


@pytest.mark.asyncio
async def test_history_empty_client(session: AsyncSession) -> None:
    from src.handlers.master.approve import cb_history

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    appt = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="pending", source="client_request",
        decision_deadline=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
    )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id))
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="history", appointment_id=appt.id)

    await cb_history(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    alert_texts = [args[0] for args, _ in cb.answered if args]
    msg_texts = [t for t, _ in msg.answers]
    all_texts = alert_texts + msg_texts
    assert any("истории" in t.lower() or "нет" in t.lower() for t in all_texts)


@pytest.mark.asyncio
async def test_history_with_long_history_uses_send_message(
    session: AsyncSession,
) -> None:
    from src.handlers.master.approve import cb_history

    master, client, service = await _seed(session)
    repo = AppointmentRepository(session)
    appt_pending = await repo.create(
        master_id=master.id, client_id=client.id, service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="pending", source="client_request",
    )
    for i in range(8):
        await repo.create(
            master_id=master.id, client_id=client.id, service_id=service.id,
            start_at=datetime(2026, 1, 1 + i, 7, 0, tzinfo=UTC),
            end_at=datetime(2026, 1, 1 + i, 8, 0, tzinfo=UTC),
            status="confirmed", source="client_request",
        )
    await session.commit()

    msg = _Msg(from_user=_User(id=master.tg_id))
    cb = _Cb(from_user=_User(id=master.tg_id), message=msg)
    bot = AsyncMock()
    cb_data = ApprovalCallback(action="history", appointment_id=appt_pending.id)

    await cb_history(cb, callback_data=cb_data, master=master, session=session, bot=bot)

    bot.send_message.assert_awaited_once()
