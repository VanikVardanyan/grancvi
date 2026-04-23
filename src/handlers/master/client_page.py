from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.client_page import (
    ClientAddApptCallback,
    ClientNotesEditCallback,
    ClientPickCallback,
)
from src.db.models import Appointment, Client, Master
from src.fsm.master_add import MasterAdd
from src.fsm.master_view import MasterView
from src.keyboards.slots import services_pick_kb
from src.repositories.clients import ClientRepository
from src.repositories.services import ServiceRepository
from src.strings import strings
from src.utils.time import now_utc

router = Router(name="master_client_page")

_MIN_SEARCH = 2
_NOTES_MAX = 500
_HISTORY_LIMIT = 20


def _search_results_kb(clients: list[Client]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for c in clients:
        label = f"{c.name} · {c.phone}" if c.phone else c.name
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=ClientPickCallback(client_id=c.id).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _client_page_kb(client_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.CLIENT_PAGE_BTN_EDIT_NOTES,
                    callback_data=ClientNotesEditCallback(client_id=client_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.CLIENT_PAGE_BTN_ADD_APPT,
                    callback_data=ClientAddApptCallback(client_id=client_id).pack(),
                )
            ],
        ]
    )


def _history_suffix(a: Appointment, now: datetime) -> str:
    if a.status == "cancelled":
        return str(strings.CLIENT_PAGE_SUFFIX_CANCELLED)
    if a.status == "rejected":
        return str(strings.CLIENT_PAGE_SUFFIX_REJECTED)
    if a.start_at > now:
        return str(strings.CLIENT_PAGE_SUFFIX_FUTURE)
    return ""


def _history_emoji(a: Appointment, now: datetime) -> str:
    if a.status in {"cancelled", "rejected", "no_show"}:
        return "❌"
    if a.start_at > now:
        return "⏳"
    return "✅"


async def _load_history(
    session: AsyncSession, *, master: Master, client_id: UUID
) -> tuple[list[Appointment], int]:
    count_stmt = (
        select(func.count())
        .select_from(Appointment)
        .where(
            Appointment.master_id == master.id,
            Appointment.client_id == client_id,
        )
    )
    total = int((await session.scalar(count_stmt)) or 0)
    stmt = (
        select(Appointment)
        .where(
            Appointment.master_id == master.id,
            Appointment.client_id == client_id,
        )
        .order_by(Appointment.start_at.desc())
        .limit(_HISTORY_LIMIT + 1)
    )
    rows = list((await session.scalars(stmt)).all())
    return rows, total


async def _render_client_page(
    *, session: AsyncSession, master: Master, client: Client
) -> tuple[str, InlineKeyboardMarkup]:
    tz = ZoneInfo(master.timezone)
    now = now_utc()
    parts: list[str] = [
        strings.CLIENT_PAGE_HEADER.format(name=client.name, phone=client.phone or "—")
    ]
    notes_text = client.notes if client.notes else strings.CLIENT_PAGE_NOTES_EMPTY
    parts.append(strings.CLIENT_PAGE_NOTES_TITLE.format(notes=notes_text))

    history, total_count = await _load_history(session, master=master, client_id=client.id)
    if not history:
        parts.append(str(strings.CLIENT_PAGE_HISTORY_EMPTY))
    else:
        truncated_extra = max(0, total_count - _HISTORY_LIMIT)
        visible_history = history[:_HISTORY_LIMIT]
        parts.append(strings.CLIENT_PAGE_HISTORY_TITLE.format(count=len(visible_history)))
        service_ids = {a.service_id for a in visible_history}
        service_names = (
            await ServiceRepository(session).get_names_by_ids(service_ids) if service_ids else {}
        )
        for a in visible_history:
            local = a.start_at.astimezone(tz)
            parts.append(
                "\n"
                + strings.CLIENT_PAGE_HISTORY_LINE.format(
                    emoji=_history_emoji(a, now),
                    dd=f"{local.day:02d}",
                    mm=f"{local.month:02d}",
                    time=local.strftime("%H:%M"),
                    service=service_names.get(a.service_id, "—"),
                    suffix=_history_suffix(a, now),
                )
            )
        if truncated_extra > 0:
            parts.append("\n" + strings.CLIENT_PAGE_HISTORY_MORE.format(n=truncated_extra))

    return "".join(parts), _client_page_kb(client.id)


@router.message(Command("client"))
async def cmd_client(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await state.clear()
    await state.set_state(MasterView.SearchingClient)
    await message.answer(strings.CLIENT_SEARCH_PROMPT)


@router.message(MasterView.SearchingClient, F.text)
async def msg_search_query(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    q = (message.text or "").strip()
    if len(q) < _MIN_SEARCH:
        await message.answer(strings.CLIENT_SEARCH_TOO_SHORT)
        return
    results = await ClientRepository(session).search_by_master(master.id, q)
    if not results:
        await message.answer(strings.CLIENT_SEARCH_EMPTY)
        return
    if len(results) == 1:
        await state.clear()
        text, kb = await _render_client_page(session=session, master=master, client=results[0])
        await message.answer(text, reply_markup=kb)
        return
    await message.answer(strings.CLIENT_SEARCH_PROMPT, reply_markup=_search_results_kb(results))


@router.callback_query(ClientPickCallback.filter())
async def cb_pick_client(
    callback: CallbackQuery,
    callback_data: ClientPickCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    client = await ClientRepository(session).get(callback_data.client_id)
    if client is None or client.master_id != master.id:
        await callback.answer(strings.CLIENT_PAGE_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    text, kb = await _render_client_page(session=session, master=master, client=client)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(text, reply_markup=kb)


@router.callback_query(ClientNotesEditCallback.filter())
async def cb_edit_notes(
    callback: CallbackQuery,
    callback_data: ClientNotesEditCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    client = await ClientRepository(session).get(callback_data.client_id)
    if client is None or client.master_id != master.id:
        await callback.answer(strings.CLIENT_PAGE_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    await state.set_state(MasterView.EditingNotes)
    await state.update_data(client_id=str(client.id))
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(strings.CLIENT_NOTES_PROMPT)


@router.message(MasterView.EditingNotes, F.text)
async def msg_notes_edit(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    data = await state.get_data()
    client_id_raw = data.get("client_id")
    if not client_id_raw:
        await state.clear()
        return
    try:
        client_id = UUID(client_id_raw)
    except ValueError:
        await state.clear()
        await message.answer(strings.CLIENT_PAGE_NOT_FOUND)
        return
    repo = ClientRepository(session)
    client = await repo.get(client_id)
    if client is None or client.master_id != master.id:
        await state.clear()
        await message.answer(strings.CLIENT_PAGE_NOT_FOUND)
        return

    raw = (message.text or "").strip()
    new_notes: str | None = None if not raw or raw == "-" else raw[:_NOTES_MAX]

    await repo.update_notes(client_id, new_notes)
    await session.commit()
    await state.clear()

    await message.answer(strings.CLIENT_NOTES_SAVED)
    await session.refresh(client)
    text, kb = await _render_client_page(session=session, master=master, client=client)
    await message.answer(text, reply_markup=kb)


@router.callback_query(ClientAddApptCallback.filter())
async def cb_add_appt(
    callback: CallbackQuery,
    callback_data: ClientAddApptCallback,
    state: FSMContext,
    session: AsyncSession,
    master: Master,
) -> None:
    await callback.answer()
    client = await ClientRepository(session).get(callback_data.client_id)
    if client is None or client.master_id != master.id:
        await callback.answer(strings.CLIENT_PAGE_NOT_FOUND, show_alert=True)
        return
    await state.clear()
    await state.set_state(MasterAdd.PickingService)
    await state.update_data(client_id=str(client.id))
    services = await ServiceRepository(session).list_active(master.id)
    if callback.message is not None and hasattr(callback.message, "answer"):
        await callback.message.answer(
            strings.MANUAL_ASK_SERVICE, reply_markup=services_pick_kb(services)
        )
