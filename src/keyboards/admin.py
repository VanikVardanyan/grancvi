from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from src.callback_data.admin import AdminMasterCallback, BlockCallback
from src.db.models import Master
from src.strings import strings


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=strings.ADMIN_MENU_MASTERS),
                KeyboardButton(text=strings.ADMIN_MENU_STATS),
            ],
            [
                KeyboardButton(text=strings.ADMIN_MENU_INVITES),
                KeyboardButton(text=strings.ADMIN_MENU_MODERATION),
            ],
            [KeyboardButton(text=strings.ADMIN_MENU_BACK)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def masters_list_kb(masters: list[Master]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for m in masters:
        is_blocked = m.blocked_at is not None
        status = (
            strings.ADMIN_MASTER_STATUS_BLOCKED
            if is_blocked
            else strings.ADMIN_MASTER_STATUS_ACTIVE
        )
        label = f"{m.slug} · {m.name} · {status}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=AdminMasterCallback(master_id=m.id, action="view").pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def block_toggle_kb(master: Master) -> InlineKeyboardMarkup:
    is_blocked = master.blocked_at is not None
    btn_text = strings.ADMIN_UNBLOCK_BTN if is_blocked else strings.ADMIN_BLOCK_BTN
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=BlockCallback(master_id=master.id, block=not is_blocked).pack(),
                )
            ]
        ]
    )
