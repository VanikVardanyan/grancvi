from __future__ import annotations

from uuid import uuid4

from src.callback_data.approval import ApprovalCallback
from src.callback_data.calendar import CalendarCallback
from src.callback_data.client_services import ClientServicePick
from src.callback_data.slots import SlotCallback


def test_calendar_pack_roundtrip() -> None:
    cb = CalendarCallback(action="pick", year=2026, month=5, day=11)
    packed = cb.pack()
    assert len(packed) <= 64
    restored = CalendarCallback.unpack(packed)
    assert restored == cb


def test_calendar_nav_uses_day_zero() -> None:
    cb = CalendarCallback(action="nav", year=2026, month=6, day=0)
    restored = CalendarCallback.unpack(cb.pack())
    assert restored.action == "nav"
    assert restored.day == 0


def test_slot_pack_roundtrip() -> None:
    cb = SlotCallback(hour=14, minute=30)
    restored = SlotCallback.unpack(cb.pack())
    assert restored == cb


def test_approval_pack_roundtrip_within_64b() -> None:
    appt_id = uuid4()
    cb = ApprovalCallback(action="confirm", appointment_id=appt_id)
    packed = cb.pack()
    assert len(packed.encode("utf-8")) <= 64
    restored = ApprovalCallback.unpack(packed)
    assert restored == cb


def test_client_service_pack_roundtrip() -> None:
    svc_id = uuid4()
    cb = ClientServicePick(service_id=svc_id)
    restored = ClientServicePick.unpack(cb.pack())
    assert restored == cb
