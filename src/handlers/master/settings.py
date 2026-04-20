from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.callback_data.settings import SettingsCallback
from src.db.models import Master
from src.keyboards.services import services_list
from src.repositories.services import ServiceRepository
from src.strings import strings

router = Router(name="master_settings")


@router.callback_query(SettingsCallback.filter())
async def handle_settings_section(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    master: Master | None,
    session: AsyncSession,
) -> None:
    if master is None:
        await callback.answer()
        return

    if callback_data.section == "services":
        repo = ServiceRepository(session)
        svcs = await repo.list_active(master.id)
        await callback.answer()
        if callback.message is not None and hasattr(callback.message, "answer"):
            title = strings.SERVICES_LIST_TITLE if svcs else strings.SERVICES_EMPTY
            await callback.message.answer(title, reply_markup=services_list(svcs))
        return

    # hours / breaks are wired in Tasks 9-10.
    await callback.answer(strings.SECTION_COMING_SOON.format(section=callback_data.section))
