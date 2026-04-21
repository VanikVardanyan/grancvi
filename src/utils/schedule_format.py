from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.mark_past import MarkPastCallback
from src.db.models import Appointment
from src.services.availability import WEEKDAYS
from src.strings import strings

_VISIBLE_STATUSES: frozenset[str] = frozenset({"pending", "confirmed", "completed", "no_show"})

_STATUS_EMOJI: dict[str, str] = {
    "pending": "⏳",
    "confirmed": "✅",
    "completed": "✅",
    "no_show": "❌",
}


def _parse_hhmm(raw: list[list[str]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in raw:
        sh, sm = s.split(":")
        eh, em = e.split(":")
        out.append((int(sh) * 60 + int(sm), int(eh) * 60 + int(em)))
    return out


def _subtract(
    windows: list[tuple[int, int]], cuts: Iterable[tuple[int, int]]
) -> list[tuple[int, int]]:
    result = list(windows)
    for cs, ce in cuts:
        if ce <= cs:
            continue
        nxt: list[tuple[int, int]] = []
        for ws, we in result:
            if ce <= ws or cs >= we:
                nxt.append((ws, we))
                continue
            if cs > ws:
                nxt.append((ws, cs))
            if ce < we:
                nxt.append((ce, we))
        result = nxt
    return result


def _format_month_short(d: date) -> str:
    return str(strings.MONTH_NAMES[d.month - 1])[:3].lower()


def _weekday_short(d: date) -> str:
    return str(strings.WEEKDAY_SHORT[d.weekday()])


def render_day_schedule(
    *,
    d: date,
    appts: list[Appointment],
    client_names: dict[UUID, str],
    service_names: dict[UUID, str],
    work_hours: dict[str, list[list[str]]],
    breaks: dict[str, list[list[str]]],
    tz: ZoneInfo,
    slot_step_min: int,
    now: datetime,
    day_nav: list[list[InlineKeyboardButton]],
) -> tuple[str, InlineKeyboardMarkup]:
    """Assemble text + keyboard for one day's schedule.

    Pure function: no DB, no bot, no wall clock (caller supplies `now`).
    """
    visible = [a for a in appts if a.status in _VISIBLE_STATUSES]
    visible.sort(key=lambda a: a.start_at)

    weekday_key = WEEKDAYS[d.weekday()]
    work_raw = work_hours.get(weekday_key) or []
    breaks_raw = breaks.get(weekday_key) or []

    header = strings.SCHED_DAY_HEADER.format(
        weekday=_weekday_short(d),
        dd=f"{d.day:02d}",
        mon=_format_month_short(d),
    )
    if not work_raw:
        hours_line = strings.SCHED_DAY_OFF_LINE
    else:
        work_windows = _parse_hhmm(work_raw)
        start_min = work_windows[0][0]
        last_end = work_windows[-1][1]
        hours_line = strings.SCHED_WORK_HOURS_LINE.format(
            start=f"{start_min // 60:02d}:{start_min % 60:02d}",
            end=f"{last_end // 60:02d}:{last_end % 60:02d}",
        )

    lines = [header, hours_line]

    if visible:
        lines.append(strings.SCHED_APPTS_SECTION.format(count=len(visible)))
        for a in visible:
            local = a.start_at.astimezone(tz)
            emoji = _STATUS_EMOJI.get(a.status, "•")
            lines.append(
                strings.SCHED_APPT_LINE.format(
                    emoji=emoji,
                    time=f"{local.hour:02d}:{local.minute:02d}",
                    client=client_names.get(a.client_id, "—"),
                    service=service_names.get(a.service_id, "—"),
                )
            )
    else:
        lines.append(strings.SCHED_APPTS_EMPTY)

    free_slots: list[datetime] = []
    if work_raw:
        day_start_local = datetime(d.year, d.month, d.day, tzinfo=tz)
        day_end_local = day_start_local + timedelta(days=1)
        work_windows = _parse_hhmm(work_raw)
        free_windows = _subtract(work_windows, _parse_hhmm(breaks_raw))

        booked_minutes: list[tuple[int, int]] = []
        blocking = [a for a in visible if a.status in ("pending", "confirmed")]
        for a in blocking:
            start_local = a.start_at.astimezone(tz)
            end_local = a.end_at.astimezone(tz)
            if end_local <= day_start_local or start_local >= day_end_local:
                continue
            cs = max(start_local, day_start_local)
            ce = min(end_local, day_end_local)
            booked_minutes.append(
                (
                    int((cs - day_start_local).total_seconds() // 60),
                    int((ce - day_start_local).total_seconds() // 60),
                )
            )
        final_free = _subtract(free_windows, booked_minutes)
        for ws, we in final_free:
            cursor = ws
            while cursor + slot_step_min <= we:
                free_slots.append(day_start_local + timedelta(minutes=cursor))
                cursor += slot_step_min

        now_local = now.astimezone(tz)
        if now_local.date() == d:
            free_slots = [s for s in free_slots if s > now_local]

    if work_raw:
        if free_slots:
            lines.append(strings.SCHED_FREE_SECTION)
            lines.append(", ".join(f"{s.hour:02d}:{s.minute:02d}" for s in free_slots))
        else:
            lines.append(strings.SCHED_FREE_NONE)

    text = "\n".join(lines)

    rows: list[list[InlineKeyboardButton]] = list(day_nav)
    now_utc = now.astimezone(UTC)
    for a in visible:
        if a.status != "confirmed" or a.end_at > now_utc:
            continue
        local = a.start_at.astimezone(tz)
        short = (client_names.get(a.client_id, "—"))[:12]
        rows.append(
            [
                InlineKeyboardButton(
                    text=strings.MARK_PAST_PRESENT.format(
                        time=f"{local.hour:02d}:{local.minute:02d}",
                        short=short,
                    ),
                    callback_data=MarkPastCallback(
                        action="present", appointment_id=a.id or uuid4()
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=strings.MARK_PAST_NO_SHOW.format(
                        time=f"{local.hour:02d}:{local.minute:02d}",
                        short=short,
                    ),
                    callback_data=MarkPastCallback(
                        action="no_show", appointment_id=a.id or uuid4()
                    ).pack(),
                ),
            ]
        )

    return text, InlineKeyboardMarkup(inline_keyboard=rows)
