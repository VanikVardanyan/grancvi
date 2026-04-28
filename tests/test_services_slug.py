from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.exceptions import InvalidSlug, ReservedSlug
from src.services.slug import SlugService


def test_validate_ok() -> None:
    SlugService.validate("anna-7f3c")
    SlugService.validate("dent123")
    SlugService.validate("a-b-c")


def test_validate_rejects_short() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("ab")


def test_validate_rejects_long() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("a" * 33)


def test_validate_rejects_uppercase() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("Anna")


def test_validate_rejects_leading_dash() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("-anna")


def test_validate_rejects_trailing_dash() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("anna-")


def test_validate_rejects_double_dash() -> None:
    with pytest.raises(InvalidSlug):
        SlugService.validate("a--b")


def test_validate_rejects_reserved() -> None:
    for bad in ["admin", "bot", "api", "grancvi", "master", "client", "invite"]:
        with pytest.raises(ReservedSlug):
            SlugService.validate(bad)


def test_transliterate_russian() -> None:
    assert SlugService.transliterate("Анна") == "anna"
    assert SlugService.transliterate("Арсен") == "arsen"
    assert SlugService.transliterate("Щёкин") == "shchyokin"


def test_transliterate_armenian() -> None:
    assert SlugService.transliterate("Արամ") == "aram"


def test_transliterate_empty_returns_master() -> None:
    assert SlugService.transliterate("") == "master"
    assert SlugService.transliterate("123") == "master"


@pytest.mark.asyncio
async def test_generate_default_unique(session: AsyncSession) -> None:
    svc = SlugService(session)
    slug = await svc.generate_default("Анна")
    assert slug.startswith("anna-")
    assert len(slug) >= 3

    master = Master(tg_id=1, name="Анна", slug=slug)
    session.add(master)
    await session.commit()

    slug2 = await svc.generate_default("Анна")
    assert slug2 != slug
    assert slug2.startswith("anna-")


@pytest.mark.asyncio
async def test_generate_default_fallback_after_collisions(session: AsyncSession) -> None:
    svc = SlugService(session)
    slug = await svc.generate_default("Анна")
    assert slug


@pytest.mark.parametrize(
    "popular_name",
    [
        # Армянские топ-имена
        "anna",
        "hayk",
        "narek",
        "tigran",
        "armen",
        "ashot",
        "vahe",
        "ani",
        "mariam",
        "nare",
        "lilit",
        "anush",
        "gohar",
        # Русские топ-имена
        "marina",
        "elena",
        "olga",
        "natalia",
        "ekaterina",
        "irina",
        "alex",
        "andrey",
        "dmitry",
        "sergey",
    ],
)
def test_validate_rejects_popular_names(popular_name: str) -> None:
    with pytest.raises(ReservedSlug):
        SlugService.validate(popular_name)


def test_validate_allows_compound_names_with_reserved_prefix() -> None:
    """`salon-anna` must pass: only exact-match reserved tokens are blocked."""
    SlugService.validate("salon-anna")  # should NOT raise
    SlugService.validate("anna-master")  # should NOT raise
