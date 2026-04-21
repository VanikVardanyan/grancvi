# ruff: noqa: RUF001
from __future__ import annotations

from src.strings import DEFAULT_LANG, get_current_lang, set_current_lang, strings


def test_set_current_lang_honors_hy() -> None:
    set_current_lang("hy")
    try:
        assert get_current_lang() == "hy"
        assert strings.MANUAL_SAVED == "✅ Գրանցումը պահպանվեց։"
    finally:
        set_current_lang(DEFAULT_LANG)


def test_set_current_lang_honors_ru() -> None:
    set_current_lang("ru")
    try:
        assert get_current_lang() == "ru"
        assert strings.MANUAL_SAVED == "✅ Запись сохранена."
    finally:
        set_current_lang(DEFAULT_LANG)


def test_set_current_lang_unknown_falls_back_to_default() -> None:
    set_current_lang("de")
    try:
        assert get_current_lang() == DEFAULT_LANG
    finally:
        set_current_lang(DEFAULT_LANG)
