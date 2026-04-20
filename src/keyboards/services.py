from __future__ import annotations

from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.services import ServiceAction
from src.db.models import Service
from src.strings import strings


def services_list(services: list[Service]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for svc in services:
        rows.append(
            [
                InlineKeyboardButton(
                    text=strings.SERVICES_ITEM_FMT.format(name=svc.name, duration=svc.duration_min),
                    callback_data=ServiceAction(action="edit", service_id=svc.id).pack(),
                ),
                InlineKeyboardButton(
                    text=strings.SERVICES_BTN_DELETE,
                    callback_data=ServiceAction(action="delete", service_id=svc.id).pack(),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.SERVICES_BTN_ADD,
                callback_data=ServiceAction(action="add").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_menu(service_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=strings.SERVICES_EDIT_BTN_NAME,
                    callback_data=ServiceAction(action="edit_name", service_id=service_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SERVICES_EDIT_BTN_DURATION,
                    callback_data=ServiceAction(
                        action="edit_duration", service_id=service_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SERVICES_EDIT_BTN_TOGGLE,
                    callback_data=ServiceAction(action="toggle", service_id=service_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=strings.SERVICES_BTN_BACK,
                    callback_data=ServiceAction(action="back").pack(),
                )
            ],
        ]
    )
