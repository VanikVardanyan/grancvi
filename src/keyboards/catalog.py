from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.catalog import CatalogMasterCallback
from src.db.models import Master
from src.strings import strings


def catalog_kb(masters: list[Master]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for m in masters:
        label = strings.CLIENT_CATALOG_CARD_FMT.format(
            name=m.name,
            specialty=m.specialty_text or "—",
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=CatalogMasterCallback(master_id=m.id).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)
