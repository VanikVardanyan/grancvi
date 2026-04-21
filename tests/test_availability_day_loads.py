from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.services.availability import calculate_day_loads

YEREVAN = ZoneInfo("Asia/Yerevan")


def test_off_day_yields_off_sentinel() -> None:
    result = calculate_day_loads(
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        booked_by_day={},
        month=date(2026, 5, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 4, 1, 0, 0, tzinfo=YEREVAN),
    )
    assert result[date(2026, 5, 1)] == -1
    assert result[date(2026, 5, 4)] == 9


def test_past_day_returns_off() -> None:
    result = calculate_day_loads(
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        booked_by_day={},
        month=date(2026, 5, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 5, 10, 12, 0, tzinfo=YEREVAN),
    )
    assert result[date(2026, 5, 4)] == -1
    assert result[date(2026, 5, 11)] == 9


def test_today_filters_past_slots() -> None:
    result = calculate_day_loads(
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        booked_by_day={},
        month=date(2026, 5, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 5, 11, 14, 30, tzinfo=YEREVAN),
    )
    assert result[date(2026, 5, 11)] == 4


def test_booked_windows_reduce_count() -> None:
    booked = {
        date(2026, 5, 4): [
            (
                datetime(2026, 5, 4, 10, 0, tzinfo=YEREVAN),
                datetime(2026, 5, 4, 11, 0, tzinfo=YEREVAN),
            ),
            (
                datetime(2026, 5, 4, 15, 0, tzinfo=YEREVAN),
                datetime(2026, 5, 4, 16, 0, tzinfo=YEREVAN),
            ),
        ]
    }
    result = calculate_day_loads(
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        booked_by_day=booked,
        month=date(2026, 5, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 4, 1, 0, 0, tzinfo=YEREVAN),
    )
    assert result[date(2026, 5, 4)] == 7


def test_returns_all_days_of_month() -> None:
    result = calculate_day_loads(
        work_hours={"mon": [["10:00", "19:00"]]},
        breaks={},
        booked_by_day={},
        month=date(2026, 2, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 1, 1, 0, 0, tzinfo=YEREVAN),
    )
    assert len(result) == 28
    assert min(result.keys()) == date(2026, 2, 1)
    assert max(result.keys()) == date(2026, 2, 28)


def test_month_with_31_days() -> None:
    result = calculate_day_loads(
        work_hours={},
        breaks={},
        booked_by_day={},
        month=date(2026, 3, 1),
        tz=YEREVAN,
        slot_step_min=60,
        service_duration_min=60,
        now=datetime(2026, 1, 1, 0, 0, tzinfo=YEREVAN),
    )
    assert len(result) == 31
