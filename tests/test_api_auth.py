from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import AsyncGenerator
from urllib.parse import urlencode

import pytest
import pytest_asyncio

from src.api.auth import InvalidInitData, parse_and_validate_init_data


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables() -> AsyncGenerator[None, None]:
    """Override DB-truncation fixture — auth tests don't touch DB."""
    yield


def _sign(data: dict[str, str], bot_token: str) -> str:
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs = sorted((k, v) for k, v in data.items() if k != "hash")
    check = "\n".join(f"{k}={v}" for k, v in pairs)
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    data["hash"] = digest
    return urlencode(data)


def test_valid_init_data_returns_user_dict() -> None:
    token = "12345:abc"
    data = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": 42, "first_name": "A"}),
    }
    raw = _sign(data, token)
    user = parse_and_validate_init_data(raw, bot_token=token)
    assert user["id"] == 42


def test_tampered_hash_rejected() -> None:
    token = "12345:abc"
    data = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": 42, "first_name": "A"}),
    }
    raw = _sign(data, token)
    # Flip the user id in the payload — data_check_string changes, hash no longer matches.
    tampered = raw.replace("%3A+42", "%3A+43", 1)
    assert tampered != raw  # sanity: replacement actually happened
    with pytest.raises(InvalidInitData):
        parse_and_validate_init_data(tampered, bot_token=token)


def test_expired_rejected() -> None:
    token = "12345:abc"
    data = {
        "auth_date": str(int(time.time()) - 48 * 3600),
        "user": json.dumps({"id": 42, "first_name": "A"}),
    }
    raw = _sign(data, token)
    with pytest.raises(InvalidInitData):
        parse_and_validate_init_data(raw, bot_token=token, max_age_seconds=24 * 3600)


def test_missing_hash_rejected() -> None:
    raw = urlencode({"auth_date": "123", "user": "{}"})
    with pytest.raises(InvalidInitData):
        parse_and_validate_init_data(raw, bot_token="12345:abc")


def test_wrong_token_rejected() -> None:
    token = "12345:abc"
    data = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": 42, "first_name": "A"}),
    }
    raw = _sign(data, token)
    with pytest.raises(InvalidInitData):
        parse_and_validate_init_data(raw, bot_token="other:xyz")
