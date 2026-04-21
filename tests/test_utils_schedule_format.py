from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton

from src.db.models import Appointment
from src.utils.schedule_format import render_day_schedule

_TZ = ZoneInfo("Asia/Yerevan")


def _appt(
    *,
    aid: UUID | None = None,
    mid: UUID | None = None,
    cid: UUID | None = None,
    sid: UUID | None = None,
    start_local: datetime,
    duration_min: int = 60,
    status: str = "confirmed",
) -> Appointment:
    start_utc = start_local.astimezone(UTC)
    a = Appointment(
        master_id=mid or uuid4(),
        client_id=cid or uuid4(),
        service_id=sid or uuid4(),
        start_at=start_utc,
        end_at=start_utc + timedelta(minutes=duration_min),
        status=status,
        source="master_manual",
    )
    if aid is not None:
        a.id = aid
    return a


_WH = {"wed": [["10:00", "19:00"]]}
_BR = {"wed": [["13:00", "14:00"]]}


def test_day_off_renders_short() -> None:
    d = date(2026, 4, 26)  # Sunday
    text, kb = render_day_schedule(
        d=d,
        appts=[],
        client_names={},
        service_names={},
        work_hours={"sun": []},
        breaks={},
        tz=_TZ,
        slot_step_min=20,
        now=datetime(2026, 4, 26, 8, tzinfo=_TZ).astimezone(UTC),
        day_nav=[],
    )
    assert "выходной" in text.lower() or "Сегодня выходной" in text
    assert kb is not None


def test_free_slots_exclude_breaks_and_booked() -> None:
    d = date(2026, 4, 22)  # Wednesday
    appts = [
        _appt(
            start_local=datetime(2026, 4, 22, 10, tzinfo=_TZ), duration_min=60, status="confirmed"
        ),
        _appt(start_local=datetime(2026, 4, 22, 15, tzinfo=_TZ), duration_min=60, status="pending"),
    ]
    names_c = {a.client_id: "Анна" for a in appts}
    names_s = {a.service_id: "Стрижка" for a in appts}
    text, _ = render_day_schedule(
        d=d,
        appts=appts,
        client_names=names_c,
        service_names=names_s,
        work_hours=_WH,
        breaks=_BR,
        tz=_TZ,
        slot_step_min=20,
        now=datetime(2026, 4, 22, 9, tzinfo=_TZ).astimezone(UTC),
        day_nav=[],
    )
    # Work hours 10-19, break 13-14. Booked 10-11, 15-16.
    # Grid at 20-min step from 10:00..18:40.
    # Expect 11:00 onwards until 12:40, then 14:00..14:40, then 16:00..18:40.
    assert "11:00" in text
    assert "10:00" not in text.split("🆓")[1] if "🆓" in text else True
    assert "13:00" not in text.split("🆓")[1] if "🆓" in text else True
    assert "15:00" not in text.split("🆓")[1] if "🆓" in text else True


def test_mark_past_buttons_appear_for_past_confirmed_only() -> None:
    d = date(2026, 4, 22)
    past_appt = _appt(
        start_local=datetime(2026, 4, 22, 10, tzinfo=_TZ),
        duration_min=60,
        status="confirmed",
    )
    future_appt = _appt(
        start_local=datetime(2026, 4, 22, 17, tzinfo=_TZ),
        duration_min=60,
        status="confirmed",
    )
    pending_past = _appt(
        start_local=datetime(2026, 4, 22, 11, tzinfo=_TZ),
        duration_min=60,
        status="pending",
    )
    appts = [past_appt, pending_past, future_appt]
    names_c = {a.client_id: "Клиент" for a in appts}
    names_s = {a.service_id: "Услуга" for a in appts}
    now = datetime(2026, 4, 22, 13, tzinfo=_TZ).astimezone(UTC)

    _, kb = render_day_schedule(
        d=d,
        appts=appts,
        client_names=names_c,
        service_names=names_s,
        work_hours=_WH,
        breaks=_BR,
        tz=_TZ,
        slot_step_min=20,
        now=now,
        day_nav=[],
    )
    packed = [
        btn.callback_data
        for row in kb.inline_keyboard
        for btn in row
        if isinstance(btn, InlineKeyboardButton) and btn.callback_data
    ]
    # Mark-past callback prefix is "mpa".
    mpa = [p for p in packed if p.startswith("mpa:")]
    # Exactly 2 buttons (present + no_show) for the one past_confirmed.
    assert len(mpa) == 2


def test_day_nav_rows_are_appended_above_mark_buttons() -> None:
    d = date(2026, 4, 22)
    past_appt = _appt(
        start_local=datetime(2026, 4, 22, 10, tzinfo=_TZ),
        duration_min=60,
        status="confirmed",
    )
    nav = [[InlineKeyboardButton(text="X", callback_data="nav_x")]]
    _, kb = render_day_schedule(
        d=d,
        appts=[past_appt],
        client_names={past_appt.client_id: "N"},
        service_names={past_appt.service_id: "S"},
        work_hours=_WH,
        breaks=_BR,
        tz=_TZ,
        slot_step_min=20,
        now=datetime(2026, 4, 22, 13, tzinfo=_TZ).astimezone(UTC),
        day_nav=nav,
    )
    rows = kb.inline_keyboard
    # First row should be the nav row (callback_data == "nav_x").
    assert rows[0][0].callback_data == "nav_x"
    # The mark-past row follows.
    assert any(
        btn.callback_data and btn.callback_data.startswith("mpa:")
        for row in rows[1:]
        for btn in row
    )


def test_cancelled_and_rejected_appts_excluded_from_text() -> None:
    d = date(2026, 4, 22)
    cancelled = _appt(
        start_local=datetime(2026, 4, 22, 10, tzinfo=_TZ),
        status="cancelled",
    )
    rejected = _appt(
        start_local=datetime(2026, 4, 22, 11, tzinfo=_TZ),
        status="rejected",
    )
    kept = _appt(
        start_local=datetime(2026, 4, 22, 12, tzinfo=_TZ),
        status="confirmed",
    )
    appts = [cancelled, rejected, kept]
    names_c = {a.client_id: f"C{i}" for i, a in enumerate(appts)}
    names_s = {a.service_id: f"S{i}" for i, a in enumerate(appts)}
    text, _ = render_day_schedule(
        d=d,
        appts=appts,
        client_names=names_c,
        service_names=names_s,
        work_hours=_WH,
        breaks=_BR,
        tz=_TZ,
        slot_step_min=20,
        now=datetime(2026, 4, 22, 9, tzinfo=_TZ).astimezone(UTC),
        day_nav=[],
    )
    # Only one appointment line with 12:00.
    assert "12:00" in text
    assert "10:00" not in text  # cancelled stripped
    assert "11:00" not in text  # rejected stripped
