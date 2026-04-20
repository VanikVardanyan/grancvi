from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

VALID_DAYS = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})
_HHMM_RE = re.compile(r"^(?P<h>\d{2}):(?P<m>\d{2})$")


class InvalidTimeFormat(ValueError):
    """Raised when a string isn't HH:MM (two digits, colon, two digits, 0-23/0-59)."""


class InvalidTimeOrder(ValueError):
    """Raised when end time is not strictly after start time."""


def parse_hhmm(raw: str) -> tuple[int, int]:
    stripped = raw.strip()
    match = _HHMM_RE.match(stripped)
    if not match:
        raise InvalidTimeFormat(stripped)
    hour = int(match.group("h"))
    minute = int(match.group("m"))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise InvalidTimeFormat(stripped)
    return (hour, minute)


def _as_minutes(hhmm: tuple[int, int]) -> int:
    return hhmm[0] * 60 + hhmm[1]


def _normalise(hhmm: tuple[int, int]) -> str:
    return f"{hhmm[0]:02d}:{hhmm[1]:02d}"


def set_day_hours(
    current: dict[str, Any],
    day: str,
    start_raw: str,
    end_raw: str,
) -> dict[str, Any]:
    """Return a new dict with `day` set to a single interval [start, end].

    Raises InvalidTimeFormat / InvalidTimeOrder. Does not mutate `current`.
    """
    if day not in VALID_DAYS:
        raise ValueError(f"unknown day: {day!r}")
    start = parse_hhmm(start_raw)
    end = parse_hhmm(end_raw)
    if _as_minutes(end) <= _as_minutes(start):
        raise InvalidTimeOrder(f"{start_raw} >= {end_raw}")
    out: dict[str, Any] = deepcopy(current)
    out[day] = [[_normalise(start), _normalise(end)]]
    return out


def set_day_off(current: dict[str, Any], day: str) -> dict[str, Any]:
    """Return a new dict with `day` removed (== day off)."""
    if day not in VALID_DAYS:
        raise ValueError(f"unknown day: {day!r}")
    out: dict[str, Any] = deepcopy(current)
    out.pop(day, None)
    return out
