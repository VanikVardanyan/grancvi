"""Google reCAPTCHA v3 server-side verify.

Stub when `recaptcha_secret` is empty — returns True so dev/test
flows aren't gated on Google credentials. Production: configure the
secret in `.env`.
"""

from __future__ import annotations

import structlog
from httpx import AsyncClient, HTTPError

from src.config import settings

log: structlog.stdlib.BoundLogger = structlog.get_logger()

_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


async def verify_recaptcha(token: str | None, expected_action: str) -> bool:
    """Verify a v3 token against Google. Returns True on success.

    No-op (returns True) when `recaptcha_secret` is unset — keeps dev
    happy. Logs every reject in production for diagnostics.
    """
    if not settings.recaptcha_secret:
        return True
    if not token:
        log.warning("recaptcha_no_token", action=expected_action)
        return False
    try:
        async with AsyncClient(timeout=5.0) as client:
            r = await client.post(
                _VERIFY_URL,
                data={"secret": settings.recaptcha_secret, "response": token},
            )
            r.raise_for_status()
            data = r.json()
    except HTTPError as exc:
        log.warning("recaptcha_http_error", err=repr(exc))
        return False

    if not data.get("success"):
        log.warning("recaptcha_failure", errors=data.get("error-codes"))
        return False
    if expected_action and data.get("action") != expected_action:
        log.warning("recaptcha_action_mismatch", got=data.get("action"), expected=expected_action)
        return False
    score = float(data.get("score", 0.0))
    if score < settings.recaptcha_min_score:
        log.warning("recaptcha_low_score", score=score, action=expected_action)
        return False
    return True
