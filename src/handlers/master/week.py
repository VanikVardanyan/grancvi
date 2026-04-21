from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.schedule import DayNavCallback, DayPickCallback
from src.db.models import Master
from src.repositories.appointments import AppointmentRepository
from src.repositories.clients import ClientRepository
from src.repositories.services import ServiceRepository
from src.services.availability import WEEKDAYS
from src.strings import strings
from src.utils.schedule_format import render_day_schedule
from src.utils.time import now_utc

router = Router(name="master_week")


def _parse_hhmm(raw: list[list[str]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for s, e in raw:
        sh, sm = s.split(":")
        eh, em = e.split(":")
        out.append((int(sh) * 60 + int(sm), int(eh) * 60 + int(em)))
    return out


def _work_minutes(
    work_hours: dict[str, list[list[str]]],
    breaks: dict[str, list[list[str]]],
    weekday_key: str,
) -> int:
    raw = work_hours.get(weekday_key) or []
    if not raw:
        return 0
    total = sum(e - s for s, e in _parse_hhmm(raw))
    br = breaks.get(weekday_key) or []
    total -= sum(e - s for s, e in _parse_hhmm(br))
    return max(0, total)


def _bar(filled: int, total: int = 8) -> str:
    filled = max(0, min(total, filled))
    return "▰" * filled + "▱" * (total - filled)


@dataclass(frozen=True)
class _DaySummary:
    d: date
    count: int
    booked_min: int
    work_min: int


async def _collect_week(
    *, session: AsyncSession, master: Master
) -> tuple[list[_DaySummary], ZoneInfo, date]:
    tz = ZoneInfo(master.timezone)
    today_local = now_utc().astimezone(tz).date()
    start = datetime(today_local.year, today_local.month, today_local.day, tzinfo=tz)
    end = start + timedelta(days=7)
    repo = AppointmentRepository(session)
    appts = await repo.list_for_master_range(
        master.id,
        start_utc=start.astimezone(UTC),
        end_utc=end.astimezone(UTC),
    )

    by_day: dict[date, list[int]] = {}
    for a in appts:
        local = a.start_at.astimezone(tz).date()
        duration = int((a.end_at - a.start_at).total_seconds() // 60)
        by_day.setdefault(local, []).append(duration)

    summaries: list[_DaySummary] = []
    for offset in range(7):
        d = today_local + timedelta(days=offset)
        rows = by_day.get(d, [])
        weekday_key = WEEKDAYS[d.weekday()]
        summaries.append(
            _DaySummary(
                d=d,
                count=len(rows),
                booked_min=sum(rows),
                work_min=_work_minutes(master.work_hours, master.breaks, weekday_key),
            )
        )
    return summaries, tz, today_local


def _week_keyboard(summaries: list[_DaySummary]) -> InlineKeyboardMarkup:
    day_buttons: list[InlineKeyboardButton] = [
        InlineKeyboardButton(
            text=strings.WEEK_BTN_DAY.format(
                wd=strings.WEEKDAY_SHORT[s.d.weekday()],
                dd=f"{s.d.day:02d}",
            ),
            callback_data=DayPickCallback(ymd=s.d.isoformat()).pack(),
        )
        for s in summaries
    ]
    rows: list[list[InlineKeyboardButton]] = [
        day_buttons[0:3],
        day_buttons[3:6],
        day_buttons[6:7],
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.DAY_NAV_TODAY,
                callback_data=DayNavCallback(action="today").pack(),
            ),
            InlineKeyboardButton(
                text=strings.DAY_NAV_CALENDAR,
                callback_data=DayNavCallback(action="calendar").pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_week(*, session: AsyncSession, master: Master) -> tuple[str, InlineKeyboardMarkup]:
    """Render the 7-day load snapshot starting from today (master's tz)."""
    summaries, _, today_local = await _collect_week(session=session, master=master)
    month_short = str(strings.MONTH_NAMES[today_local.month - 1])[:3].lower()
    lines = [
        strings.WEEK_HEADER.format(dd=f"{today_local.day:02d}", mon=month_short),
        "",
    ]
    for s in summaries:
        wd = str(strings.WEEKDAY_SHORT[s.d.weekday()])
        if s.work_min <= 0:
            lines.append(
                strings.WEEK_DAY_LINE_OFF.format(
                    wd=wd,
                    dd=f"{s.d.day:02d}",
                    mm=f"{s.d.month:02d}",
                    bar=_bar(0),
                )
            )
            continue
        ratio = s.booked_min / s.work_min
        filled = round(ratio * 8)
        pct = round(ratio * 100)
        lines.append(
            strings.WEEK_DAY_LINE.format(
                wd=wd,
                dd=f"{s.d.day:02d}",
                mm=f"{s.d.month:02d}",
                count=s.count,
                bar=_bar(filled),
                pct=pct,
            )
        )
    return "\n".join(lines), _week_keyboard(summaries)


@router.message(Command("week"))
async def cmd_week(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await state.clear()
    text, kb = await render_week(session=session, master=master)
    await message.answer(text, reply_markup=kb)


@router.callback_query(DayPickCallback.filter())
async def cb_day_pick(
    callback: CallbackQuery,
    callback_data: DayPickCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    picked = date.fromisoformat(callback_data.ymd)

    tz = ZoneInfo(master.timezone)
    day_start_utc = datetime(picked.year, picked.month, picked.day, tzinfo=tz).astimezone(UTC)
    day_end_utc = day_start_utc + timedelta(days=1)
    repo = AppointmentRepository(session)
    appts = await repo.list_for_master_range(
        master.id,
        start_utc=day_start_utc,
        end_utc=day_end_utc,
        statuses=("pending", "confirmed", "completed", "no_show"),
    )

    client_ids = {a.client_id for a in appts}
    service_ids = {a.service_id for a in appts}
    client_names = await ClientRepository(session).get_names_by_ids(client_ids)
    service_names = await ServiceRepository(session).get_names_by_ids(service_ids)

    day_nav = [
        [
            InlineKeyboardButton(
                text=strings.DAY_NAV_BACK_TO_WEEK,
                callback_data=DayNavCallback(action="week").pack(),
            ),
            InlineKeyboardButton(
                text=strings.DAY_NAV_CALENDAR,
                callback_data=DayNavCallback(action="calendar").pack(),
            ),
        ]
    ]
    text, kb = render_day_schedule(
        d=picked,
        appts=appts,
        client_names=client_names,
        service_names=service_names,
        work_hours=master.work_hours,
        breaks=master.breaks,
        tz=tz,
        slot_step_min=master.slot_step_min,
        now=now_utc(),
        day_nav=day_nav,
    )
    from src.handlers.master.today import _safe_edit  # local import avoids cycle

    if isinstance(callback.message, Message):
        await _safe_edit(callback.message, text, kb)
