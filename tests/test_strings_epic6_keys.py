from __future__ import annotations

from src.strings import DEFAULT_LANG, set_current_lang, strings

_KEYS = [
    "SCHED_DAY_HEADER",
    "SCHED_WORK_HOURS_LINE",
    "SCHED_DAY_OFF_LINE",
    "SCHED_APPTS_SECTION",
    "SCHED_APPTS_EMPTY",
    "SCHED_APPT_LINE",
    "SCHED_FREE_SECTION",
    "SCHED_FREE_NONE",
    "DAY_NAV_TODAY",
    "DAY_NAV_TOMORROW",
    "DAY_NAV_WEEK",
    "DAY_NAV_CALENDAR",
    "DAY_NAV_ADD",
    "DAY_NAV_BACK_TO_WEEK",
    "DAY_NAV_BACK_TO_CALENDAR",
    "MARK_PAST_PRESENT",
    "MARK_PAST_NO_SHOW",
    "MARK_PAST_OK_COMPLETED",
    "MARK_PAST_OK_NO_SHOW",
    "MARK_PAST_NOT_AVAILABLE",
    "MARK_PAST_NOT_ENDED",
    "MARK_PAST_ALREADY_CLOSED",
    "WEEK_HEADER",
    "WEEK_DAY_LINE",
    "WEEK_DAY_LINE_OFF",
    "WEEK_BTN_DAY",
    "CLIENT_SEARCH_PROMPT",
    "CLIENT_SEARCH_TOO_SHORT",
    "CLIENT_SEARCH_EMPTY",
    "CLIENT_PAGE_HEADER",
    "CLIENT_PAGE_NOTES_TITLE",
    "CLIENT_PAGE_NOTES_EMPTY",
    "CLIENT_PAGE_HISTORY_TITLE",
    "CLIENT_PAGE_HISTORY_EMPTY",
    "CLIENT_PAGE_HISTORY_LINE",
    "CLIENT_PAGE_HISTORY_MORE",
    "CLIENT_PAGE_SUFFIX_FUTURE",
    "CLIENT_PAGE_SUFFIX_CANCELLED",
    "CLIENT_PAGE_SUFFIX_REJECTED",
    "CLIENT_PAGE_BTN_EDIT_NOTES",
    "CLIENT_PAGE_BTN_ADD_APPT",
    "CLIENT_PAGE_NOT_FOUND",
    "CLIENT_NOTES_PROMPT",
    "CLIENT_NOTES_SAVED",
]


def test_epic6_keys_resolve_ru() -> None:
    set_current_lang("ru")
    try:
        for k in _KEYS:
            assert isinstance(getattr(strings, k), str), k
    finally:
        set_current_lang(DEFAULT_LANG)


def test_epic6_keys_resolve_hy() -> None:
    set_current_lang("hy")
    try:
        for k in _KEYS:
            assert isinstance(getattr(strings, k), str), k
    finally:
        set_current_lang(DEFAULT_LANG)
