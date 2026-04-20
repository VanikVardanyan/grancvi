from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

YEREVAN = ZoneInfo("Asia/Yerevan")


def now_utc() -> datetime:
    """Tz-aware 'now' in UTC. Keeps wall-clock access in one place."""
    return datetime.now(UTC)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed")
    return dt.astimezone(UTC)


def to_yerevan(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed")
    return dt.astimezone(YEREVAN)
