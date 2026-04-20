from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from src.utils.time import YEREVAN, now_utc, to_utc, to_yerevan


def test_yerevan_constant_is_asia_yerevan() -> None:
    assert ZoneInfo("Asia/Yerevan") == YEREVAN


def test_now_utc_is_tz_aware_and_utc() -> None:
    got = now_utc()
    assert got.tzinfo is not None
    assert got.utcoffset() == datetime(2026, 1, 1, tzinfo=UTC).utcoffset()


def test_to_utc_converts_from_local_tz() -> None:
    local = datetime(2026, 4, 20, 14, 0, tzinfo=YEREVAN)
    assert to_utc(local) == datetime(2026, 4, 20, 10, 0, tzinfo=UTC)


def test_to_yerevan_converts_from_utc() -> None:
    utc = datetime(2026, 4, 20, 10, 0, tzinfo=UTC)
    assert to_yerevan(utc) == datetime(2026, 4, 20, 14, 0, tzinfo=YEREVAN)


def test_to_utc_rejects_naive() -> None:
    with pytest.raises(ValueError):
        to_utc(datetime(2026, 4, 20, 14, 0))


def test_to_yerevan_rejects_naive() -> None:
    with pytest.raises(ValueError):
        to_yerevan(datetime(2026, 4, 20, 14, 0))
