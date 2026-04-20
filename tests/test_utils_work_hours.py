from __future__ import annotations

import pytest

from src.utils.work_hours import (
    InvalidTimeFormat,
    InvalidTimeOrder,
    parse_hhmm,
    set_day_hours,
    set_day_off,
)


def test_parse_hhmm_valid() -> None:
    assert parse_hhmm("10:00") == (10, 0)
    assert parse_hhmm("09:30") == (9, 30)
    assert parse_hhmm("23:59") == (23, 59)
    assert parse_hhmm("00:00") == (0, 0)


def test_parse_hhmm_with_whitespace() -> None:
    assert parse_hhmm("  10:00  ") == (10, 0)


@pytest.mark.parametrize(
    "bad",
    ["", "10", "10:", ":00", "25:00", "10:60", "abc", "10:5", "1:00", "10.00"],
)
def test_parse_hhmm_invalid(bad: str) -> None:
    with pytest.raises(InvalidTimeFormat):
        parse_hhmm(bad)


def test_set_day_hours_empty_state() -> None:
    result = set_day_hours({}, "mon", "10:00", "19:00")
    assert result == {"mon": [["10:00", "19:00"]]}


def test_set_day_hours_overwrites_existing() -> None:
    current: dict[str, list[list[str]]] = {"mon": [["09:00", "18:00"]]}
    result = set_day_hours(current, "mon", "10:00", "19:00")
    assert result == {"mon": [["10:00", "19:00"]]}


def test_set_day_hours_rejects_end_before_start() -> None:
    with pytest.raises(InvalidTimeOrder):
        set_day_hours({}, "mon", "19:00", "10:00")


def test_set_day_hours_rejects_end_equal_to_start() -> None:
    with pytest.raises(InvalidTimeOrder):
        set_day_hours({}, "mon", "10:00", "10:00")


def test_set_day_off_removes_entry() -> None:
    current: dict[str, list[list[str]]] = {"mon": [["10:00", "19:00"]], "tue": [["11:00", "20:00"]]}
    result = set_day_off(current, "mon")
    assert result == {"tue": [["11:00", "20:00"]]}


def test_set_day_off_noop_when_absent() -> None:
    assert set_day_off({}, "sun") == {}


def test_immutable_does_not_mutate_input() -> None:
    original: dict[str, list[list[str]]] = {"mon": [["09:00", "18:00"]]}
    set_day_hours(original, "tue", "10:00", "19:00")
    assert original == {"mon": [["09:00", "18:00"]]}  # unchanged
