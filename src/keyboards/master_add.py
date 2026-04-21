from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.approval import ApprovalCallback
from src.callback_data.master_add import (
    CustomTimeCallback,
    PhoneDupCallback,
    RecentClientCallback,
    SkipCommentCallback,
)
from src.callback_data.slots import SlotCallback
from src.db.models import Client
from src.strings import strings


def _client_button(client: Client) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=f"{client.name} · {client.phone}",
        callback_data=RecentClientCallback(client_id=str(client.id)).pack(),
    )


def _control_row_for_picker() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=strings.MANUAL_BTN_SEARCH,
            callback_data=RecentClientCallback(client_id="search").pack(),
        ),
        InlineKeyboardButton(
            text=strings.MANUAL_BTN_NEW,
            callback_data=RecentClientCallback(client_id="new").pack(),
        ),
    ]


def recent_clients_kb(clients: list[Client]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [[_client_button(c)] for c in clients]
    rows.append(_control_row_for_picker())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_results_kb(clients: list[Client]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [[_client_button(c)] for c in clients]
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.MANUAL_BTN_SEARCH_CANCEL,
                callback_data="master_add_search_cancel",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def phone_dup_kb(client_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.MANUAL_BTN_DUP_USE,
                    callback_data=PhoneDupCallback(action="use", client_id=client_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.MANUAL_BTN_DUP_RETRY,
                    callback_data=PhoneDupCallback(action="retry", client_id=client_id).pack(),
                )
            ],
        ]
    )


def slots_grid_with_custom(slots: list[datetime], *, tz: ZoneInfo) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []
    for slot in slots:
        local = slot.astimezone(tz)
        current.append(
            InlineKeyboardButton(
                text=f"{local.hour:02d}:{local.minute:02d}",
                callback_data=SlotCallback(hour=local.hour, minute=local.minute).pack(),
            )
        )
        if len(current) == 3:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.MANUAL_BTN_CUSTOM_TIME,
                callback_data=CustomTimeCallback().pack(),
            ),
            InlineKeyboardButton(
                text=strings.MANUAL_BTN_BACK,
                callback_data="master_add_back",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_comment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.MANUAL_BTN_SKIP,
                    callback_data=SkipCommentCallback().pack(),
                )
            ]
        ]
    )


def confirm_add_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.MANUAL_BTN_SAVE,
                    callback_data="master_add_save",
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.MANUAL_BTN_CANCEL,
                    callback_data="master_add_cancel",
                )
            ],
        ]
    )


def client_cancel_kb(appointment_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.CLIENT_CANCEL_BUTTON,
                    callback_data=ApprovalCallback(
                        action="cancel", appointment_id=appointment_id
                    ).pack(),
                )
            ]
        ]
    )
