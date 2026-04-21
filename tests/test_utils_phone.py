from __future__ import annotations

import pytest

from src.utils.phone import normalize


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+374 99 12 34 56", "+37499123456"),
        ("+37499123456", "+37499123456"),
        ("+374-99-12-34-56", "+37499123456"),
        ("+374 (99) 12 34 56", "+37499123456"),
        ("099 12 34 56", "+37499123456"),
        ("099-123-456", "+37499123456"),
        (" +374  99 123 456 ", "+37499123456"),
    ],
)
def test_normalize_valid(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "abc",
        "+1 212 555 1212",  # not +374
        "+37499",  # too short
        "+374991234567",  # too long
        "99123456",  # missing leading 0 and country code
        "++37499123456",  # malformed
    ],
)
def test_normalize_rejects(raw: str) -> None:
    assert normalize(raw) is None
