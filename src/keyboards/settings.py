from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.settings import SettingsCallback
from src.strings import strings


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_SERVICES,
                    callback_data=SettingsCallback(section="services").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_WORK_HOURS,
                    callback_data=SettingsCallback(section="hours").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SETTINGS_BTN_BREAKS,
                    callback_data=SettingsCallback(section="breaks").pack(),
                )
            ],
        ]
    )
