"""Exits 0 if bot can reach Telegram API, 1 otherwise.

Called by Docker HEALTHCHECK every 60s.
Uses stdlib only to avoid adding an HTTP-client dependency.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("BOT_TOKEN not set", file=sys.stderr)
        return 1
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=8.0) as resp:
            body = resp.read()
    except urllib.error.URLError as exc:
        print(f"getMe failed: {exc}", file=sys.stderr)
        return 1
    except TimeoutError as exc:
        print(f"getMe timed out: {exc}", file=sys.stderr)
        return 1

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        print(f"getMe response not JSON: {exc}", file=sys.stderr)
        return 1

    if not data.get("ok"):
        print(f"Telegram returned ok=false: {data}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
