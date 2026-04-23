from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from src.config import settings


class InvalidInitData(Exception):
    """Raised when a Telegram WebApp initData string fails HMAC validation."""


def parse_and_validate_init_data(
    raw: str, *, bot_token: str, max_age_seconds: int = 24 * 3600
) -> dict[str, Any]:
    """Verify a Telegram WebApp initData string and return the parsed `user` dict.

    See https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not raw:
        raise InvalidInitData("empty")

    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    provided_hash = pairs.pop("hash", None)
    if not provided_hash:
        raise InvalidInitData("missing hash")

    check_str = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check_str.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, provided_hash):
        raise InvalidInitData("hash mismatch")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise InvalidInitData("bad auth_date") from exc
    if abs(time.time() - auth_date) > max_age_seconds:
        raise InvalidInitData("expired")

    user_raw = pairs.get("user")
    if not user_raw:
        raise InvalidInitData("missing user")
    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise InvalidInitData("bad user json") from exc
    if not isinstance(user, dict):
        raise InvalidInitData("user is not an object")
    return user


async def require_tg_user(
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
) -> dict[str, Any]:
    """FastAPI dependency: extract & validate user from X-Telegram-Init-Data header."""
    if not settings.app_bot_token:
        raise HTTPException(status_code=503, detail="app_bot_token not configured")
    try:
        return parse_and_validate_init_data(x_telegram_init_data, bot_token=settings.app_bot_token)
    except InvalidInitData as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
