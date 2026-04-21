from __future__ import annotations

from uuid import uuid4

from src.callback_data.client_page import (
    ClientAddApptCallback,
    ClientNotesEditCallback,
    ClientPickCallback,
)
from src.callback_data.mark_past import MarkPastCallback
from src.callback_data.master_calendar import MasterCalendarCallback
from src.callback_data.schedule import DayNavCallback, DayPickCallback


def test_pack_under_64_bytes() -> None:
    cid = uuid4()
    for payload in [
        DayPickCallback(ymd="2026-04-25").pack(),
        DayNavCallback(action="today").pack(),
        MarkPastCallback(action="present", appointment_id=cid).pack(),
        MasterCalendarCallback(action="pick", year=2026, month=5, day=3).pack(),
        ClientPickCallback(client_id=cid).pack(),
        ClientNotesEditCallback(client_id=cid).pack(),
        ClientAddApptCallback(client_id=cid).pack(),
    ]:
        assert len(payload.encode("utf-8")) <= 64, payload


def test_roundtrip_mark_past() -> None:
    cid = uuid4()
    packed = MarkPastCallback(action="no_show", appointment_id=cid).pack()
    restored = MarkPastCallback.unpack(packed)
    assert restored.action == "no_show"
    assert restored.appointment_id == cid


def test_prefix_does_not_collide_with_client_calendar() -> None:
    # Existing CalendarCallback has prefix "cal"; MasterCalendarCallback uses "mca".
    mca = MasterCalendarCallback(action="noop", year=2026, month=1, day=0).pack()
    assert mca.startswith("mca:")
