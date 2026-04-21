from __future__ import annotations

from calendar import monthrange
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.master_calendar import MasterCalendarCallback
from src.callback_data.schedule import DayNavCallback
from src.db.models import Master
from src.repositories.appointments import AppointmentRepository
from src.repositories.clients import ClientRepository
from src.repositories.services import ServiceRepository
from src.services.availability import WEEKDAYS
from src.strings import strings
from src.utils.schedule_format import render_day_schedule
from src.utils.time import now_utc

router = Router(name="master_calendar")


def _noop_btn(text: str, year: int, month: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=MasterCalendarCallback(action="noop", year=year, month=month, day=0).pack(),
    )


def _shift_month(d: date, by: int) -> date:
    total = d.year * 12 + (d.month - 1) + by
    return date(total // 12, (total % 12) + 1, 1)


async def _month_load(*, session: AsyncSession, master: Master, month: date) -> dict[date, int]:
    """Return per-day appointment count for the month (negative for days off)."""
    tz = ZoneInfo(master.timezone)
    first = datetime(month.year, month.month, 1, tzinfo=tz)
    last = _shift_month(month, +1)
    last_dt = datetime(last.year, last.month, 1, tzinfo=tz)
    repo = AppointmentRepository(session)
    appts = await repo.list_for_master_range(
        master.id,
        start_utc=first.astimezone(UTC),
        end_utc=last_dt.astimezone(UTC),
        statuses=("pending", "confirmed", "completed", "no_show"),
    )

    _, days_in_month = monthrange(month.year, month.month)
    counts: dict[date, int] = {}
    for day_num in range(1, days_in_month + 1):
        d = date(month.year, month.month, day_num)
        wk = WEEKDAYS[d.weekday()]
        counts[d] = -1 if not master.work_hours.get(wk) else 0
    for a in appts:
        local_day = a.start_at.astimezone(tz).date()
        if counts.get(local_day, -1) >= 0:
            counts[local_day] += 1
    return counts


def _month_keyboard(*, month: date, counts: dict[date, int], today: date) -> InlineKeyboardMarkup:
    year, month_num = month.year, month.month
    month_name = str(strings.MONTH_NAMES[month_num - 1])

    prev_shift = _shift_month(month, -1)
    next_shift = _shift_month(month, +1)
    header = [
        InlineKeyboardButton(
            text="«",
            callback_data=MasterCalendarCallback(
                action="nav", year=prev_shift.year, month=prev_shift.month, day=0
            ).pack(),
        ),
        _noop_btn(f"{month_name} {year}", year, month_num),
        InlineKeyboardButton(
            text="»",
            callback_data=MasterCalendarCallback(
                action="nav", year=next_shift.year, month=next_shift.month, day=0
            ).pack(),
        ),
    ]
    weekday_row = [_noop_btn(lbl, year, month_num) for lbl in strings.WEEKDAY_SHORT]
    rows: list[list[InlineKeyboardButton]] = [header, weekday_row]

    _, days_in_month = monthrange(year, month_num)
    first_weekday = date(year, month_num, 1).weekday()

    cells: list[InlineKeyboardButton] = [
        _noop_btn(" ", year, month_num) for _ in range(first_weekday)
    ]
    for day in range(1, days_in_month + 1):
        d = date(year, month_num, day)
        count = counts.get(d, -1)
        if count < 0:
            emoji = "⚫"
        elif count == 0:
            emoji = "🟢"
        elif count < 5:
            emoji = "🟡"
        else:
            emoji = "🔴"
        label = f"{emoji}{day}"
        if count < 0:
            cells.append(_noop_btn(label, year, month_num))
        else:
            cells.append(
                InlineKeyboardButton(
                    text=label,
                    callback_data=MasterCalendarCallback(
                        action="pick", year=year, month=month_num, day=day
                    ).pack(),
                )
            )
    while len(cells) % 7 != 0:
        cells.append(_noop_btn(" ", year, month_num))
    for i in range(0, len(cells), 7):
        rows.append(cells[i : i + 7])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_calendar(
    *, session: AsyncSession, master: Master, month: date | None
) -> tuple[str, InlineKeyboardMarkup]:
    tz = ZoneInfo(master.timezone)
    today_local = now_utc().astimezone(tz).date()
    effective_month = month or today_local.replace(day=1)
    counts = await _month_load(session=session, master=master, month=effective_month)
    kb = _month_keyboard(month=effective_month, counts=counts, today=today_local)
    header_name = str(strings.MONTH_NAMES[effective_month.month - 1])
    text = f"🗓 {header_name} {effective_month.year}"
    return text, kb


@router.message(Command("calendar"))
async def cmd_calendar(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await state.clear()
    text, kb = await render_calendar(session=session, master=master, month=None)
    await message.answer(text, reply_markup=kb)


async def _render_day(
    *, session: AsyncSession, master: Master, d: date
) -> tuple[str, InlineKeyboardMarkup]:
    tz = ZoneInfo(master.timezone)
    day_start_utc = datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(UTC)
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
    client_names = (
        await ClientRepository(session).get_names_by_ids(client_ids) if client_ids else {}
    )
    service_names = (
        await ServiceRepository(session).get_names_by_ids(service_ids) if service_ids else {}
    )

    day_nav = [
        [
            InlineKeyboardButton(
                text=strings.DAY_NAV_BACK_TO_CALENDAR,
                callback_data=DayNavCallback(action="calendar").pack(),
            )
        ]
    ]
    return render_day_schedule(
        d=d,
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


@router.callback_query(MasterCalendarCallback.filter())
async def cb_master_calendar(
    callback: CallbackQuery,
    callback_data: MasterCalendarCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    from src.handlers.master.today import _safe_edit  # local import avoids cycle

    await callback.answer()
    if callback_data.action == "noop":
        return
    if callback_data.action == "nav":
        month = date(callback_data.year, callback_data.month, 1)
        text, kb = await render_calendar(session=session, master=master, month=month)
        if isinstance(callback.message, Message):
            await _safe_edit(callback.message, text, kb)
        return
    # pick
    d = date(callback_data.year, callback_data.month, callback_data.day)
    text, kb = await _render_day(session=session, master=master, d=d)
    if isinstance(callback.message, Message):
        await _safe_edit(callback.message, text, kb)
