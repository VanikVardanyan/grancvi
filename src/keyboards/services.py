from __future__ import annotations

from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.callback_data.services import ServiceAction, ServicePresetPick
from src.db.models import Service
from src.strings import strings

_PRESETS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "dentist": ("CLEANING", "FILLING", "EXTRACTION", "WHITENING", "CROWN"),
    "hair": ("HAIRCUT", "COLORING", "STYLING", "BEARD", "HIGHLIGHTS"),
    "nails": ("MANICURE", "PEDICURE", "GEL", "NAIL_EXT"),
    "cosmetologist": ("FACE_CLEANING", "PEELING", "MASSAGE", "BOTOX"),
}

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dentist": ("стомат", "ատամնաբույժ", "ատամ"),
    "hair": ("парикмахер", "стилист", "վարսահարդար", "վարսավիր"),
    "nails": ("маник", "педик", "մանիկյուր", "մատնահարդար"),
    "cosmetologist": ("косметолог", "կոսմետոլոգ"),
}


def _detect_category(specialty: str) -> str | None:
    s = (specialty or "").lower()
    for category, kws in _CATEGORY_KEYWORDS.items():
        if any(kw in s for kw in kws):
            return category
    return None


def service_presets_for(specialty: str) -> list[tuple[str, str]]:
    """Return list of (key, label) pairs for the specialty's presets.

    Keys are lowercased preset names (stable across locales). Labels are
    looked up from strings in the current language.
    """
    category = _detect_category(specialty)
    if category is None:
        return []
    result: list[tuple[str, str]] = []
    for key_upper in _PRESETS_BY_CATEGORY[category]:
        label = getattr(strings, f"SERVICE_PRESET_{key_upper}")
        result.append((key_upper.lower(), label))
    return result


def service_presets_kb(specialty: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    buf: list[InlineKeyboardButton] = []
    for key, label in service_presets_for(specialty):
        buf.append(
            InlineKeyboardButton(text=label, callback_data=ServicePresetPick(key=key).pack())
        )
        if len(buf) == 2:
            rows.append(buf)
            buf = []
    if buf:
        rows.append(buf)
    rows.append(
        [
            InlineKeyboardButton(
                text=strings.SERVICES_ADD_CUSTOM_BTN,
                callback_data=ServicePresetPick(key="custom").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
