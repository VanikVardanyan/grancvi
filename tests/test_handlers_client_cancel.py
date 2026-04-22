from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.approval import ApprovalCallback
from src.db.models import Appointment, Client, Master, Reminder, Service
from src.handlers.client.cancel import handle_cancel


@dataclass
class _FakeUser:
    id: int


@dataclass
class _FakeMsg:
    edited_markup: bool = False

    async def edit_reply_markup(self, *, reply_markup: Any = None) -> None:
        self.edited_markup = True


@dataclass
class _FakeCb:
    from_user: _FakeUser
    message: _FakeMsg = field(default_factory=_FakeMsg)
    answered: list[tuple[str, bool]] = field(default_factory=list)

    async def answer(self, text: str = "", show_alert: bool = False) -> None:
        self.answered.append((text, show_alert))


async def _seed(session: AsyncSession, *, client_tg: int | None = 9001) -> Appointment:
    master = Master(tg_id=9100, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Анна", phone="+37499111111", tg_id=client_tg)
    session.add(client)
    service = Service(master_id=master.id, name="Стрижка", duration_min=60)
    session.add(service)
    await session.flush()
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
        end_at=datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
        status="confirmed",
        source="master_manual",
    )
    session.add(appt)
    await session.flush()
    await session.commit()
    return appt


@pytest.mark.asyncio
async def test_cancel_happy_path_notifies_master(session: AsyncSession) -> None:
    appt = await _seed(session)
    bot = AsyncMock()
    cb = _FakeCb(from_user=_FakeUser(id=9001))

    await handle_cancel(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ApprovalCallback(action="cancel", appointment_id=appt.id),
        session=session,
        bot=bot,
    )
    bot.send_message.assert_awaited_once()
    assert cb.message.edited_markup is True
    assert cb.answered  # at least one answer call
    # The bot.send_message kwargs should carry a chat_id matching master tg
    _, kwargs = bot.send_message.call_args
    assert kwargs["chat_id"] == 9100


@pytest.mark.asyncio
async def test_cancel_wrong_tg_alerts_unavailable(session: AsyncSession) -> None:
    appt = await _seed(session)
    bot = AsyncMock()
    cb = _FakeCb(from_user=_FakeUser(id=12345))

    await handle_cancel(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ApprovalCallback(action="cancel", appointment_id=appt.id),
        session=session,
        bot=bot,
    )
    bot.send_message.assert_not_awaited()
    # alert was raised
    assert any(show for _, show in cb.answered)


@pytest.mark.asyncio
async def test_cancel_missing_appt_alerts_unavailable(session: AsyncSession) -> None:
    bot = AsyncMock()
    cb = _FakeCb(from_user=_FakeUser(id=9001))

    await handle_cancel(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ApprovalCallback(action="cancel", appointment_id=uuid4()),
        session=session,
        bot=bot,
    )
    bot.send_message.assert_not_awaited()
    assert any(show for _, show in cb.answered)


@pytest.mark.asyncio
async def test_client_cancel_suppresses_reminders(session: AsyncSession) -> None:
    appt = await _seed(session)
    reminder = Reminder(
        appointment_id=appt.id,
        kind="day_before",
        send_at=datetime(2026, 5, 3, 12, 0, tzinfo=UTC),
    )
    session.add(reminder)
    await session.commit()

    bot = AsyncMock()
    cb = _FakeCb(from_user=_FakeUser(id=9001))

    await handle_cancel(
        callback=cb,  # type: ignore[arg-type]
        callback_data=ApprovalCallback(action="cancel", appointment_id=appt.id),
        session=session,
        bot=bot,
    )

    await session.refresh(reminder)
    assert reminder.sent is True
