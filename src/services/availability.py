from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _parse_intervals(raw: list[list[str]]) -> list[tuple[int, int]]:
    """[['10:00','19:00'], ...] → [(600, 1140), ...] (minutes from midnight)."""
    out: list[tuple[int, int]] = []
    for start_s, end_s in raw:
        sh, sm = start_s.split(":")
        eh, em = end_s.split(":")
        out.append((int(sh) * 60 + int(sm), int(eh) * 60 + int(em)))
    return out


def _subtract(windows: list[tuple[int, int]], cuts: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Remove each `cut` interval from every window, returning surviving fragments."""
    result = list(windows)
    for c_start, c_end in cuts:
        if c_end <= c_start:
            # zero / negative duration — leave windows alone
            continue
        next_result: list[tuple[int, int]] = []
        for w_start, w_end in result:
            # No overlap
            if c_end <= w_start or c_start >= w_end:
                next_result.append((w_start, w_end))
                continue
            # Left fragment
            if c_start > w_start:
                next_result.append((w_start, c_start))
            # Right fragment
            if c_end < w_end:
                next_result.append((c_end, w_end))
        result = next_result
    return result


def calculate_free_slots(
    work_hours: dict[str, list[list[str]]],
    breaks: dict[str, list[list[str]]],
    booked: list[tuple[datetime, datetime]],
    day: date,
    tz: ZoneInfo,
    slot_step_min: int,
    service_duration_min: int,
    now: datetime | None = None,
) -> list[datetime]:
    """Return tz-aware start times (in `tz`) of every slot that fits the service.

    Pure function — no DB, no clock access. Caller must pass `now` if they want
    past slots filtered for today; otherwise the function never looks at wall time.
    """
    weekday = WEEKDAYS[day.weekday()]
    work_raw = work_hours.get(weekday)
    if not work_raw:
        return []

    work_windows = _parse_intervals(work_raw)
    break_windows = _parse_intervals(breaks.get(weekday, []))

    free_windows = _subtract(work_windows, break_windows)

    day_start_local = datetime(day.year, day.month, day.day, tzinfo=tz)
    day_end_local = day_start_local + timedelta(days=1)

    booked_minutes: list[tuple[int, int]] = []
    for start_at, end_at in booked:
        start_local = start_at.astimezone(tz)
        end_local = end_at.astimezone(tz)
        # Ignore bookings entirely outside this day.
        if end_local <= day_start_local or start_local >= day_end_local:
            continue
        clipped_start = max(start_local, day_start_local)
        clipped_end = min(end_local, day_end_local)
        s_min = int((clipped_start - day_start_local).total_seconds() // 60)
        e_min = int((clipped_end - day_start_local).total_seconds() // 60)
        booked_minutes.append((s_min, e_min))

    free_windows = _subtract(free_windows, booked_minutes)

    slots: list[datetime] = []
    for w_start, w_end in free_windows:
        cursor = w_start
        while cursor + service_duration_min <= w_end:
            slots.append(day_start_local + timedelta(minutes=cursor))
            cursor += slot_step_min

    if now is not None:
        now_local = now.astimezone(tz)
        if now_local.date() == day:
            slots = [s for s in slots if s > now_local]

    return slots


def calculate_day_loads(
    *,
    work_hours: dict[str, list[list[str]]],
    breaks: dict[str, list[list[str]]],
    booked_by_day: dict[date, list[tuple[datetime, datetime]]],
    month: date,
    tz: ZoneInfo,
    slot_step_min: int,
    service_duration_min: int,
    now: datetime,
) -> dict[date, int]:
    """Count free slots for every day of `month`.

    Returns {date: count} where count is:
      -1 — day is off (no work_hours for that weekday) or entirely in the past.
      0  — fully booked.
      N  — N free slots of the requested duration still fit that day.

    Pure: reuses `calculate_free_slots` per day; `booked_by_day` pre-groups
    appointments by local date so callers don't have to re-partition them.
    """
    _, days_in_month = monthrange(month.year, month.month)
    now_date = now.astimezone(tz).date()

    result: dict[date, int] = {}
    for day_num in range(1, days_in_month + 1):
        d = date(month.year, month.month, day_num)
        if d < now_date:
            result[d] = -1
            continue
        weekday = WEEKDAYS[d.weekday()]
        if not work_hours.get(weekday):
            result[d] = -1
            continue
        slots = calculate_free_slots(
            work_hours=work_hours,
            breaks=breaks,
            booked=booked_by_day.get(d, []),
            day=d,
            tz=tz,
            slot_step_min=slot_step_min,
            service_duration_min=service_duration_min,
            now=now if d == now_date else None,
        )
        result[d] = len(slots)
    return result
