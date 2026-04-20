from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from src.services.availability import calculate_free_slots

YEREVAN = ZoneInfo("Asia/Yerevan")

# Monday 2026-04-20 is the anchor date for most tests.
MON = date(2026, 4, 20)

WORK_MON_10_19: dict[str, list[list[str]]] = {"mon": [["10:00", "19:00"]]}
NO_BREAKS: dict[str, list[list[str]]] = {}


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _yer(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=YEREVAN)


def test_day_off_returns_empty() -> None:
    # No entry for "mon" in work_hours at all → day off.
    result = calculate_free_slots(
        work_hours={},
        breaks=NO_BREAKS,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=20,
        service_duration_min=30,
    )
    assert result == []


def test_empty_day_full_grid() -> None:
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    # 10, 11, 12, 13, 14, 15, 16, 17, 18 (18+60 == 19 fits)
    assert [s.hour for s in result] == [10, 11, 12, 13, 14, 15, 16, 17, 18]
    assert result[0] == _yer(2026, 4, 20, 10)
    assert result[-1] == _yer(2026, 4, 20, 18)


def test_booking_in_middle_splits_window() -> None:
    # 13:00-14:00 Yerevan = 09:00-10:00 UTC
    booked = [(_utc(2026, 4, 20, 9), _utc(2026, 4, 20, 10))]
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=booked,
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert [s.hour for s in result] == [10, 11, 12, 14, 15, 16, 17, 18]


def test_break_lunch_splits_window() -> None:
    breaks = {"mon": [["13:00", "14:00"]]}
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=breaks,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert [s.hour for s in result] == [10, 11, 12, 14, 15, 16, 17, 18]


def test_today_past_slots_filtered() -> None:
    # "now" is 14:30 Yerevan on the same day — slots at 14:00 and earlier are dropped.
    now = _yer(2026, 4, 20, 14, 30)
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=now,
    )
    assert [s.hour for s in result] == [15, 16, 17, 18]


def test_past_filter_not_applied_to_future_day() -> None:
    # "now" is on Mon, but we're querying Tue — past filter must be skipped.
    now = _yer(2026, 4, 20, 14, 30)
    tue = date(2026, 4, 21)
    result = calculate_free_slots(
        work_hours={"tue": [["10:00", "19:00"]]},
        breaks=NO_BREAKS,
        booked=[],
        day=tue,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=now,
    )
    assert len(result) == 9


def test_service_too_long_returns_empty() -> None:
    result = calculate_free_slots(
        work_hours={"mon": [["10:00", "11:00"]]},
        breaks=NO_BREAKS,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=20,
        service_duration_min=120,
    )
    assert result == []


def test_booking_at_window_start_removes_first_slot() -> None:
    # 10:00-11:00 Yerevan = 06:00-07:00 UTC
    booked = [(_utc(2026, 4, 20, 6), _utc(2026, 4, 20, 7))]
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=booked,
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert [s.hour for s in result] == [11, 12, 13, 14, 15, 16, 17, 18]


def test_booking_at_window_end_removes_last_slot() -> None:
    # 18:00-19:00 Yerevan = 14:00-15:00 UTC
    booked = [(_utc(2026, 4, 20, 14), _utc(2026, 4, 20, 15))]
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=booked,
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert [s.hour for s in result] == [10, 11, 12, 13, 14, 15, 16, 17]


def test_split_day_morning_and_evening() -> None:
    # Two intervals: 10-13 and 15-19. 13-15 is neither work nor break — just a gap.
    wh = {"mon": [["10:00", "13:00"], ["15:00", "19:00"]]}
    result = calculate_free_slots(
        work_hours=wh,
        breaks=NO_BREAKS,
        booked=[],
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert [s.hour for s in result] == [10, 11, 12, 15, 16, 17, 18]


def test_booking_entirely_outside_work_window_ignored() -> None:
    # 08:00-09:00 Yerevan — before the 10:00 work start. Must not crash or clip anything.
    booked = [(_utc(2026, 4, 20, 4), _utc(2026, 4, 20, 5))]
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=booked,
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert len(result) == 9


def test_zero_duration_booking_does_not_remove_slots() -> None:
    # A booked tuple with start == end — defensive: shouldn't blow up.
    booked = [(_utc(2026, 4, 20, 9), _utc(2026, 4, 20, 9))]
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=booked,
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert len(result) == 9


def test_booking_on_different_day_ignored() -> None:
    # Booking on Sunday (day before) — entirely outside MON → must be skipped via continue.
    # 2026-04-19 UTC is still 2026-04-19 in Yerevan, so end_local <= day_start_local.
    booked = [(_utc(2026, 4, 19, 10), _utc(2026, 4, 19, 11))]
    result = calculate_free_slots(
        work_hours=WORK_MON_10_19,
        breaks=NO_BREAKS,
        booked=booked,
        day=MON,
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
    )
    assert len(result) == 9
