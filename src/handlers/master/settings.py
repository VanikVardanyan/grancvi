from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery

from src.callback_data.settings import SettingsCallback
from src.strings import strings

router = Router(name="master_settings")


@router.callback_query(SettingsCallback.filter())
async def handle_settings_section(callback: CallbackQuery, callback_data: SettingsCallback) -> None:
    # Filled in by Tasks 6 (services), 9 (hours). For now acknowledge and stub.
    await callback.answer(strings.SECTION_COMING_SOON.format(section=callback_data.section))
