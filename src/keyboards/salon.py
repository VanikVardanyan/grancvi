from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from src.strings import strings


def salon_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=strings.SALON_MENU_MY_MASTERS),
                KeyboardButton(text=strings.SALON_MENU_INVITE_MASTER),
            ],
            [KeyboardButton(text=strings.SALON_MENU_ADD_APPT)],
            [
                KeyboardButton(text=strings.SALON_MENU_MY_LINK),
                KeyboardButton(text=strings.SALON_MENU_QR),
            ],
            [KeyboardButton(text=strings.SALON_MENU_SETTINGS)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
