from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Salon
from src.repositories.salons import SalonRepository


@pytest.mark.asyncio
async def test_create_salon(session: AsyncSession) -> None:
    repo = SalonRepository(session)
    salon = await repo.create(owner_tg_id=42, name="Hair World", slug="hair-world")
    await session.commit()
    assert salon.id is not None
    assert salon.slug == "hair-world"


@pytest.mark.asyncio
async def test_get_by_slug(session: AsyncSession) -> None:
    session.add(Salon(owner_tg_id=1, name="A", slug="aaa-1"))
    await session.commit()
    repo = SalonRepository(session)
    found = await repo.by_slug("aaa-1")
    assert found is not None and found.slug == "aaa-1"
    assert await repo.by_slug("nope") is None


@pytest.mark.asyncio
async def test_get_by_owner_tg_id(session: AsyncSession) -> None:
    session.add(Salon(owner_tg_id=77, name="A", slug="s77"))
    await session.commit()
    repo = SalonRepository(session)
    found = await repo.by_owner_tg_id(77)
    assert found is not None and found.owner_tg_id == 77
    assert await repo.by_owner_tg_id(99) is None


@pytest.mark.asyncio
async def test_list_masters(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=1, name="S", slug="s1")
    session.add(salon)
    await session.flush()
    session.add_all(
        [
            Master(tg_id=101, name="A", slug="a-1", salon_id=salon.id),
            Master(tg_id=102, name="B", slug="b-1", salon_id=salon.id),
            Master(tg_id=103, name="C", slug="c-1"),
        ]
    )
    await session.commit()
    repo = SalonRepository(session)
    masters = await repo.list_masters(salon.id)
    slugs = sorted(m.slug for m in masters)
    assert slugs == ["a-1", "b-1"]
