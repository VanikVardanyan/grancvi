from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.registration import SlugConfirmCallback, SpecialtyHintCallback
from src.strings import strings


def specialty_hints_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.REGISTER_SPECIALTY_HINT_HAIR,
                    callback_data=SpecialtyHintCallback(hint="hair").pack(),
                ),
                InlineKeyboardButton(
                    text=strings.REGISTER_SPECIALTY_HINT_DENTIST,
                    callback_data=SpecialtyHintCallback(hint="dentist").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=strings.REGISTER_SPECIALTY_HINT_NAILS,
                    callback_data=SpecialtyHintCallback(hint="nails").pack(),
                ),
                InlineKeyboardButton(
                    text=strings.REGISTER_SPECIALTY_HINT_COSMETOLOGIST,
                    callback_data=SpecialtyHintCallback(hint="cosmetologist").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=strings.REGISTER_SPECIALTY_HINT_CUSTOM,
                    callback_data=SpecialtyHintCallback(hint="custom").pack(),
                ),
            ],
        ]
    )


def slug_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.REGISTER_SLUG_USE_BTN,
                    callback_data=SlugConfirmCallback(action="use").pack(),
                ),
                InlineKeyboardButton(
                    text=strings.REGISTER_SLUG_CHANGE_BTN,
                    callback_data=SlugConfirmCallback(action="change").pack(),
                ),
            ]
        ]
    )
