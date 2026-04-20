from __future__ import annotations

import pytest

from src.config import Settings


def test_settings_loads_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/d")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
    monkeypatch.setenv("ADMIN_TG_IDS", "111,222,333")

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.bot_token == "test-token"
    assert s.database_url == "postgresql+asyncpg://u:p@h/d"
    assert s.redis_url == "redis://h:6379/0"
    assert s.admin_tg_ids == [111, 222, 333]
    assert s.default_timezone == "Asia/Yerevan"
    assert s.log_level == "INFO"


def test_settings_empty_admin_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "t")
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("REDIS_URL", "y")
    monkeypatch.setenv("ADMIN_TG_IDS", "")

    s = Settings(_env_file=None)  # type: ignore[call-arg]

    assert s.admin_tg_ids == []
