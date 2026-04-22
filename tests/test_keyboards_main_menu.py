from __future__ import annotations

from src.keyboards.common import main_menu
from src.strings import get_bundle


def _all_button_texts() -> list[str]:
    kb = main_menu()
    return [btn.text for row in kb.keyboard for btn in row]


def test_main_menu_contains_all_master_sections_in_ru() -> None:
    ru = get_bundle("ru")
    texts = _all_button_texts()
    expected = {
        ru.MAIN_MENU_TODAY,
        ru.MAIN_MENU_TOMORROW,
        ru.MAIN_MENU_WEEK,
        ru.MAIN_MENU_CALENDAR,
        ru.MAIN_MENU_ADD,
        ru.MAIN_MENU_CLIENT,
        ru.MAIN_MENU_SETTINGS,
    }
    assert expected.issubset(set(texts))


def test_main_menu_is_persistent_and_resized() -> None:
    kb = main_menu()
    assert kb.is_persistent is True
    assert kb.resize_keyboard is True


def test_main_menu_contains_my_link_button_in_ru() -> None:
    ru = get_bundle("ru")
    texts = _all_button_texts()
    assert ru.MAIN_MENU_MY_LINK in texts
