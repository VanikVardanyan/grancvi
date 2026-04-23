from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Salon
from src.services.slug import SlugService


@pytest.mark.asyncio
async def test_master_slug_rejected_if_taken_by_salon(session: AsyncSession) -> None:
    session.add(Salon(owner_tg_id=1, name="S", slug="conflict"))
    await session.commit()
    svc = SlugService(session)
    taken = await svc.is_taken("conflict")
    assert taken is True


@pytest.mark.asyncio
async def test_salon_slug_rejected_if_taken_by_master(session: AsyncSession) -> None:
    session.add(Master(tg_id=1, name="M", slug="mine-0001"))
    await session.commit()
    svc = SlugService(session)
    taken = await svc.is_taken("mine-0001")
    assert taken is True


@pytest.mark.asyncio
async def test_fresh_slug_is_not_taken(session: AsyncSession) -> None:
    svc = SlugService(session)
    assert await svc.is_taken("fresh-slug") is False


@pytest.mark.asyncio
async def test_generate_default_skips_salon_occupied(session: AsyncSession) -> None:
    # Pre-populate salons with many collisions under a base — verify generate_default
    # does not return a slug occupied by a salon.
    session.add(Salon(owner_tg_id=1, name="Anna", slug="anna-aaaa"))
    session.add(Salon(owner_tg_id=2, name="Anna", slug="anna-bbbb"))
    await session.commit()
    svc = SlugService(session)
    slug = await svc.generate_default("Anna")
    assert slug not in {"anna-aaaa", "anna-bbbb"}
