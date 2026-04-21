from __future__ import annotations

import re

_ALLOWED = re.compile(r"[^\d+]")


def normalize(raw: str) -> str | None:
    """Normalize an Armenian phone to E.164 (+374XXXXXXXX).

    Returns None if `raw` cannot be parsed as an Armenian mobile number.
    Accepts `+374 XX XXX XXX`, `+374XXXXXXXX`, `0XX XXX XXX` variants with
    spaces, dashes, or parentheses. Rejects foreign country codes and wrong
    lengths.
    """
    if not raw:
        return None
    cleaned = _ALLOWED.sub("", raw.strip())
    if not cleaned:
        return None
    if cleaned.startswith("+"):
        digits = cleaned[1:]
        if not digits.isdigit():
            return None
        if not digits.startswith("374"):
            return None
        national = digits[3:]
    else:
        if not cleaned.isdigit():
            return None
        if cleaned.startswith("0"):
            national = cleaned[1:]
        elif cleaned.startswith("374"):
            national = cleaned[3:]
        else:
            return None
    if len(national) != 8:
        return None
    return f"+374{national}"
