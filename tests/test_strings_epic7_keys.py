from __future__ import annotations

import pytest

from src.strings import get_bundle

EPIC7_KEYS = [
    "REMINDER_CLIENT_DAY_BEFORE",
    "REMINDER_CLIENT_TWO_HOURS",
    "REMINDER_MASTER_BEFORE",
    "REMINDER_PENDING_EXPIRED",
]


@pytest.mark.parametrize("lang", ["ru", "hy"])
def test_epic7_keys_present(lang: str) -> None:
    bundle = get_bundle(lang)
    for key in EPIC7_KEYS:
        assert hasattr(bundle, key), f"{lang}: missing {key}"
        assert isinstance(getattr(bundle, key), str)


def test_reminder_day_before_has_time_and_service_placeholders() -> None:
    template = get_bundle("ru").REMINDER_CLIENT_DAY_BEFORE
    assert "{time}" in template
    assert "{service}" in template


def test_reminder_two_hours_has_time_and_service_placeholders() -> None:
    template = get_bundle("ru").REMINDER_CLIENT_TWO_HOURS
    assert "{time}" in template
    assert "{service}" in template


def test_reminder_master_has_required_placeholders() -> None:
    template = get_bundle("ru").REMINDER_MASTER_BEFORE
    assert "{time}" in template
    assert "{service}" in template
    assert "{client_name}" in template
    assert "{phone}" in template


def test_reminder_pending_expired_has_required_placeholders() -> None:
    template = get_bundle("ru").REMINDER_PENDING_EXPIRED
    assert "{date}" in template
    assert "{time}" in template
    assert "{service}" in template
