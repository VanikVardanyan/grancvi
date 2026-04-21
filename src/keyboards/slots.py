from __future__ import annotations

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.approval import ApprovalCallback
from src.callback_data.client_services import ClientServicePick
from src.callback_data.slots import SlotCallback
from src.db.models import Service
from src.strings import strings


def slots_grid(slots: list[datetime], *, tz: ZoneInfo) -> InlineKeyboardMarkup:
    """Render 3-per-row HH:MM buttons, plus a trailing Back row."""
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
        [InlineKeyboardButton(text=strings.CLIENT_BTN_BACK, callback_data="client_back")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.CLIENT_BTN_CONFIRM, callback_data="client_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.CLIENT_BTN_CANCEL, callback_data="client_cancel"
                )
            ],
        ]
    )


def services_pick_kb(services: list[Service]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for svc in services:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{svc.name} · {svc.duration_min} мин",
                    callback_data=ClientServicePick(service_id=svc.id).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def approval_kb(appointment_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.APPT_BTN_CONFIRM,
                    callback_data=ApprovalCallback(
                        action="confirm", appointment_id=appointment_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=strings.APPT_BTN_REJECT,
                    callback_data=ApprovalCallback(
                        action="reject", appointment_id=appointment_id
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=strings.APPT_BTN_HISTORY,
                    callback_data=ApprovalCallback(
                        action="history", appointment_id=appointment_id
                    ).pack(),
                )
            ],
        ]
    )
