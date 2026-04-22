from __future__ import annotations

import re
import secrets
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.exceptions import InvalidSlug, ReservedSlug

_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MIN: Final[int] = 3
_MAX: Final[int] = 32

_RESERVED: Final[frozenset[str]] = frozenset(
    {"admin", "bot", "api", "grancvi", "master", "client", "invite"}
)

# Russian + Armenian to latin.
_RU_MAP: Final[dict[str, str]] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
_HY_MAP: Final[dict[str, str]] = {
    "ա": "a", "բ": "b", "գ": "g", "դ": "d", "ե": "e", "զ": "z", "է": "e",
    "ը": "y", "թ": "t", "ժ": "zh", "ի": "i", "լ": "l", "խ": "kh", "ծ": "ts",
    "կ": "k", "հ": "h", "ձ": "dz", "ղ": "gh", "ճ": "ch", "մ": "m", "յ": "y",
    "ն": "n", "շ": "sh", "ո": "o", "չ": "ch", "պ": "p", "ջ": "j", "ռ": "r",
    "ս": "s", "վ": "v", "տ": "t", "ր": "r", "ց": "ts", "ու": "u", "փ": "p",
    "ք": "k", "և": "ev", "օ": "o", "ֆ": "f",
}


class SlugService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def validate(slug: str) -> None:
        if slug in _RESERVED:
            raise ReservedSlug(slug)
        if not (_MIN <= len(slug) <= _MAX):
            raise InvalidSlug(f"length must be {_MIN}..{_MAX}")
        if not _SLUG_RE.match(slug):
            raise InvalidSlug("must match ^[a-z0-9]+(-[a-z0-9]+)*$")

    @staticmethod
    def transliterate(text: str) -> str:
        s = text.strip().lower()
        out: list[str] = []
        for ch in s:
            if ch in _RU_MAP:
                out.append(_RU_MAP[ch])
            elif ch in _HY_MAP:
                out.append(_HY_MAP[ch])
            elif ch.isascii() and ch.isalnum():
                out.append(ch)
            elif ch == " " or ch == "-":
                out.append("-")
            # else: drop
        cleaned = re.sub(r"-+", "-", "".join(out)).strip("-")
        # Must start with letter and be >=3 chars non-digit
        if not cleaned or cleaned.isdigit():
            return "master"
        # Ensure at least 3 chars prefix
        if len(cleaned) < 3:
            cleaned = cleaned + "-" + secrets.token_hex(2)
        return cleaned

    async def generate_default(self, first_name: str) -> str:
        base = self.transliterate(first_name)
        for _ in range(5):
            suffix = secrets.token_hex(2)  # 4 hex chars
            candidate = f"{base}-{suffix}"
            if len(candidate) > _MAX:
                candidate = candidate[:_MAX].rstrip("-")
            try:
                self.validate(candidate)
            except (InvalidSlug, ReservedSlug):
                continue
            existing = await self._session.scalar(
                select(Master).where(Master.slug == candidate)
            )
            if existing is None:
                return candidate
        # Fallback: master-<6hex>
        return f"master-{secrets.token_hex(3)}"
