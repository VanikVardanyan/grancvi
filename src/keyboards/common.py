from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from src.callback_data.register import LangPickCallback
from src.strings import strings


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=strings.MAIN_MENU_TODAY),
                KeyboardButton(text=strings.MAIN_MENU_TOMORROW),
            ],
            [
                KeyboardButton(text=strings.MAIN_MENU_WEEK),
                KeyboardButton(text=strings.MAIN_MENU_CALENDAR),
            ],
            [
                KeyboardButton(text=strings.MAIN_MENU_ADD),
                KeyboardButton(text=strings.MAIN_MENU_CLIENT),
            ],
            [
                KeyboardButton(text=strings.MAIN_MENU_MY_LINK),
                KeyboardButton(text=strings.MAIN_MENU_SETTINGS),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def lang_picker() -> InlineKeyboardMarkup:
    # Both button labels come from either bundle (they're identical emoji-prefixed names).
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.LANG_BTN_RU,
                    callback_data=LangPickCallback(lang="ru").pack(),
                ),
                InlineKeyboardButton(
                    text=strings.LANG_BTN_HY,
                    callback_data=LangPickCallback(lang="hy").pack(),
                ),
            ]
        ]
    )
