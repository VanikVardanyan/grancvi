from __future__ import annotations

from src.keyboards.common import main_menu
from src.strings import get_bundle


def _all_button_texts() -> list[str]:
    kb = main_menu()
    return [btn.text for row in kb.keyboard for btn in row]


def test_main_menu_contains_core_master_sections_in_ru() -> None:
    ru = get_bundle("ru")
    texts = _all_button_texts()
    expected = {
        ru.MAIN_MENU_TODAY,
        ru.MAIN_MENU_TOMORROW,
        ru.MAIN_MENU_CALENDAR,
        ru.MAIN_MENU_ADD,
        ru.MAIN_MENU_SETTINGS,
        ru.MAIN_MENU_MY_LINK,
        ru.MAIN_MENU_QR,
    }
    assert expected.issubset(set(texts))


def test_main_menu_is_persistent_and_resized() -> None:
    kb = main_menu()
    assert kb.is_persistent is True
    assert kb.resize_keyboard is True


def test_main_menu_contains_my_link_and_qr_buttons_in_ru() -> None:
    ru = get_bundle("ru")
    texts = _all_button_texts()
    assert ru.MAIN_MENU_MY_LINK in texts
    assert ru.MAIN_MENU_QR in texts


def test_main_menu_drops_week_and_client_search_buttons() -> None:
    ru = get_bundle("ru")
    hy = get_bundle("hy")
    texts = set(_all_button_texts())
    for absent in (
        ru.MAIN_MENU_WEEK,
        ru.MAIN_MENU_CLIENT,
        hy.MAIN_MENU_WEEK,
        hy.MAIN_MENU_CLIENT,
    ):
        assert absent not in texts
