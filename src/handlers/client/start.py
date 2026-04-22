from __future__ import annotations

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.fsm.client_booking import ClientBooking
from src.handlers.client.catalog import render_catalog
from src.keyboards.slots import services_pick_kb
from src.repositories.masters import MasterRepository
from src.repositories.services import ServiceRepository
from src.strings import strings

router = Router(name="client_start")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


def _parse_payload(text: str | None) -> str:
    if not text:
        return ""
    parts = text.split(maxsplit=1)
    return parts[1] if len(parts) == 2 else ""


@router.message(CommandStart())
async def handle_start(
    message: Message,
    master: Master | None,
    state: FSMContext,
    session: AsyncSession,
    command: CommandObject | None = None,
) -> None:
    """Entry point for any user whose tg_id is not the master's.

    The master's own `/start` is handled by `handlers/master/start.py` which runs
    before this router (master router is registered first). When this handler runs,
    `master` middleware value is always None by construction.
    """
    if master is not None:
        return  # master router handled it

    if command and command.args:
        payload = command.args
    else:
        payload = _parse_payload(message.text)

    m_repo = MasterRepository(session)

    if payload.startswith("master_"):
        slug = payload[len("master_"):]
        target = await m_repo.by_slug(slug)
        if target is None or target.blocked_at is not None or not target.is_public:
            await message.answer(strings.CLIENT_MASTER_NOT_FOUND)
            await render_catalog(message=message, session=session)
            return

        s_repo = ServiceRepository(session)
        services = await s_repo.list_active(target.id)
        if not services:
            await message.answer(strings.CLIENT_NO_SERVICES)
            return
        await state.clear()
        await state.set_state(ClientBooking.ChoosingService)
        await state.update_data(master_id=str(target.id))
        await message.answer(
            strings.CLIENT_MASTER_CARD_FMT.format(
                name=target.name, specialty=target.specialty_text or "—"
            )
        )
        await message.answer(
            strings.CLIENT_CHOOSE_SERVICE, reply_markup=services_pick_kb(services)
        )
        log.info("client_start_deep_link", tg_id=message.from_user.id if message.from_user else None)
        return

    await render_catalog(message=message, session=session)


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(strings.CLIENT_CANCELLED)
