"""PostHog analytics shim.

Centralized so call sites stay clean: `track_event(distinct_id, "X")`
either fires a PostHog event or no-ops silently when `POSTHOG_API_KEY`
is unset (local dev, tests). PostHog client is lazy-initialized on
first use so importing this module costs nothing.

We intentionally pick PostHog's EU instance by default (`eu.i.posthog.com`)
since the user base is in Armenia/EU and that keeps data residency
predictable. Override via `POSTHOG_HOST` in env if needed.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.config import settings

log: structlog.stdlib.BoundLogger = structlog.get_logger()

_client: Any = None  # posthog.Posthog | None — kept Any to avoid hard-dep at import time


def _get_client() -> Any:
    global _client
    if _client is not None:
        return _client
    if not settings.posthog_api_key:
        return None
    try:
        from posthog import Posthog  # type: ignore[import-not-found]

        _client = Posthog(
            project_api_key=settings.posthog_api_key,
            host=settings.posthog_host,
            # We control flushes ourselves via fire-and-forget — buffered sends
            # would lose events on a fast container restart.
            sync_mode=False,
        )
        return _client
    except Exception as exc:
        log.warning("posthog_init_failed", err=repr(exc))
        return None


def track_event(
    distinct_id: str | int,
    event: str,
    properties: dict[str, Any] | None = None,
) -> None:
    """Send a custom event to PostHog. No-ops if analytics is unconfigured.

    `distinct_id` should be the Telegram user id (as int or str) so events
    from the bot, the TMA and the public API stitch together against the
    same person in the PostHog UI.
    """
    client = _get_client()
    if client is None:
        return
    try:
        client.capture(
            distinct_id=str(distinct_id),
            event=event,
            properties=properties or {},
        )
    except Exception as exc:
        log.info("posthog_capture_failed", event_name=event, err=repr(exc))
