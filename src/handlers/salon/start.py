from __future__ import annotations

from datetime import UTC, datetime

import structlog
from aiogram import Router
from aiogram.filters import CommandStart, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Salon
from src.fsm.salon_register import SalonRegister
from src.keyboards.common import lang_picker
from src.keyboards.salon import salon_main_menu
from src.repositories.invites import InviteRepository
from src.strings import strings

router = Router(name="salon_start")
log: structlog.stdlib.BoundLogger = structlog.get_logger()


def _parse_invite(text: str | None) -> str | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) != 2:
        return None
    payload = parts[1]
    return payload[len("invite_") :] if payload.startswith("invite_") else None


class HasSalonInviteOrOwner(Filter):
    async def __call__(
        self,
        event: Message,
        salon: Salon | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        if salon is not None:
            return True
        code = _parse_invite(event.text)
        if code is None or session is None:
            return False
        repo = InviteRepository(session)
        invite = await repo.by_code(code)
        return invite is not None and invite.kind == "salon_owner"


@router.message(CommandStart(), HasSalonInviteOrOwner())
async def handle_salon_start(
    message: Message,
    salon: Salon | None,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    code = _parse_invite(message.text)
    if code is not None and salon is None:
        repo = InviteRepository(session)
        invite = await repo.by_code(code)
        if invite is None:
            await message.answer(strings.INVITE_NOT_FOUND)
            return
        if invite.used_at is not None:
            await message.answer(strings.INVITE_ALREADY_USED)
            return
        if invite.expires_at <= datetime.now(UTC):
            await message.answer(strings.INVITE_EXPIRED)
            return
        await state.clear()
        await state.update_data(invite_code=code)
        await state.set_state(SalonRegister.waiting_lang)
        await message.answer(strings.LANG_PICK_PROMPT, reply_markup=lang_picker())
        return

    if salon is not None:
        await state.clear()
        await message.answer(strings.SALON_WELCOME_BACK, reply_markup=salon_main_menu())
