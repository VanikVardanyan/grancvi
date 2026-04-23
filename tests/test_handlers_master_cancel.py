from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from aiogram.types import InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.master_cancel import MasterCancelCallback
from src.db.models import Appointment, Client, Master, Service
from src.handlers.master.cancel import cb_master_cancel


async def _seed(
    session: AsyncSession, status: str, hours_from_now: int
) -> tuple[Master, Appointment, Client, Service]:
    master = Master(tg_id=7700, name="M", slug="m-test", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="Anna", phone="+37499000000", tg_id=8800)
    session.add(client)
    service = Service(master_id=master.id, name="Cut", duration_min=30)
    session.add(service)
    await session.flush()
    start = datetime.now(UTC) + timedelta(hours=hours_from_now)
    appt = Appointment(
        master_id=master.id,
        client_id=client.id,
        service_id=service.id,
        start_at=start,
        end_at=start + timedelta(minutes=30),
        status=status,
        source="master_manual",
    )
    session.add(appt)
    await session.flush()
    await session.commit()
    return master, appt, client, service


def _cb(master_tg: int) -> AsyncMock:
    cb = AsyncMock()
    cb.from_user = MagicMock(id=master_tg)
    cb.message = MagicMock(spec=Message)
    cb.message.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    return cb


@pytest.mark.asyncio
async def test_ask_shows_confirmation_dialog(session: AsyncSession) -> None:
    master, appt, _, _ = await _seed(session, status="confirmed", hours_from_now=3)
    cb = _cb(master.tg_id)
    bot = AsyncMock()

    await cb_master_cancel(
        callback=cb,
        callback_data=MasterCancelCallback(action="ask", appointment_id=appt.id),
        session=session,
        master=master,
        bot=bot,
    )
    # Should edit the message with a confirmation dialog + inline keyboard of 2 buttons
    cb.message.edit_text.assert_awaited()
    call_kwargs = cb.message.edit_text.await_args.kwargs
    kb = call_kwargs.get("reply_markup")
    assert isinstance(kb, InlineKeyboardMarkup)
    assert len(kb.inline_keyboard[0]) == 2


@pytest.mark.asyncio
async def test_confirm_cancels_appointment_and_notifies_client(session: AsyncSession) -> None:
    master, appt, client, _ = await _seed(session, status="confirmed", hours_from_now=3)
    cb = _cb(master.tg_id)
    bot = AsyncMock()

    await cb_master_cancel(
        callback=cb,
        callback_data=MasterCancelCallback(action="confirm", appointment_id=appt.id),
        session=session,
        master=master,
        bot=bot,
    )

    await session.refresh(appt)
    assert appt.status == "cancelled"
    assert appt.cancelled_by == "master"
    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.kwargs["chat_id"] == client.tg_id


@pytest.mark.asyncio
async def test_cannot_cancel_past_appointment(session: AsyncSession) -> None:
    master, appt, _, _ = await _seed(session, status="confirmed", hours_from_now=-3)
    cb = _cb(master.tg_id)
    bot = AsyncMock()

    await cb_master_cancel(
        callback=cb,
        callback_data=MasterCancelCallback(action="ask", appointment_id=appt.id),
        session=session,
        master=master,
        bot=bot,
    )
    # Ask on a past appt → alert, not edit
    cb.answer.assert_awaited()
    cb.message.edit_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_cannot_cancel_other_masters_appointment(session: AsyncSession) -> None:
    _, appt, _, _ = await _seed(session, status="confirmed", hours_from_now=3)
    master_b = Master(tg_id=9900, name="B", slug="b-test", timezone="Asia/Yerevan")
    session.add(master_b)
    await session.commit()

    cb = _cb(master_b.tg_id)
    bot = AsyncMock()
    await cb_master_cancel(
        callback=cb,
        callback_data=MasterCancelCallback(action="confirm", appointment_id=appt.id),
        session=session,
        master=master_b,
        bot=bot,
    )
    await session.refresh(appt)
    assert appt.status == "confirmed"


@pytest.mark.asyncio
async def test_abort_does_not_cancel(session: AsyncSession) -> None:
    master, appt, _, _ = await _seed(session, status="confirmed", hours_from_now=3)
    cb = _cb(master.tg_id)
    bot = AsyncMock()

    await cb_master_cancel(
        callback=cb,
        callback_data=MasterCancelCallback(action="abort", appointment_id=appt.id),
        session=session,
        master=master,
        bot=bot,
    )
    await session.refresh(appt)
    assert appt.status == "confirmed"


@pytest.mark.asyncio
async def test_confirm_suppresses_reminders(session: AsyncSession) -> None:
    from src.db.models import Reminder

    master, appt, _, _ = await _seed(session, status="confirmed", hours_from_now=24)
    reminder = Reminder(
        appointment_id=appt.id,
        send_at=datetime.now(UTC) + timedelta(hours=22),
        kind="two_hours",
        channel="telegram",
        sent=False,
    )
    session.add(reminder)
    await session.commit()

    cb = _cb(master.tg_id)
    bot = AsyncMock()
    await cb_master_cancel(
        callback=cb,
        callback_data=MasterCancelCallback(action="confirm", appointment_id=appt.id),
        session=session,
        master=master,
        bot=bot,
    )

    await session.refresh(reminder)
    assert reminder.sent is True


def test_master_cancel_callback_uuid_roundtrip() -> None:
    uid = UUID("12345678-1234-5678-1234-567812345678")
    packed = MasterCancelCallback(action="ask", appointment_id=uid).pack()
    unpacked = MasterCancelCallback.unpack(packed)
    assert unpacked.action == "ask"
    assert unpacked.appointment_id == uid
