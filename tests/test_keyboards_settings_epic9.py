from __future__ import annotations

from src.keyboards.settings import settings_menu
from src.strings import get_bundle


def _all_texts() -> list[str]:
    kb = settings_menu()
    return [b.text for row in kb.inline_keyboard for b in row]


def test_settings_has_profile_button() -> None:
    ru = get_bundle("ru")
    assert ru.SETTINGS_BTN_PROFILE in _all_texts()


def test_settings_has_my_invites_button() -> None:
    ru = get_bundle("ru")
    assert ru.SETTINGS_BTN_MY_INVITES in _all_texts()


def test_settings_has_new_invite_button() -> None:
    ru = get_bundle("ru")
    assert ru.SETTINGS_BTN_NEW_INVITE in _all_texts()
