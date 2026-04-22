from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master
from src.repositories.masters import MasterRepository


@pytest.mark.asyncio
async def test_by_slug_found(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="anna-0001")
    session.add(m)
    await session.commit()
    repo = MasterRepository(session)
    found = await repo.by_slug("anna-0001")
    assert found is not None and found.tg_id == 1


@pytest.mark.asyncio
async def test_by_slug_missing(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    assert await repo.by_slug("nope") is None


@pytest.mark.asyncio
async def test_list_public_excludes_blocked(session: AsyncSession) -> None:
    session.add(Master(tg_id=1, name="A", slug="a-0001", is_public=True))
    session.add(
        Master(
            tg_id=2, name="B", slug="b-0001",
            is_public=True, blocked_at=datetime.now(timezone.utc),
        )
    )
    session.add(Master(tg_id=3, name="C", slug="c-0001", is_public=False))
    session.add(Master(tg_id=4, name="D", slug="d-0001", is_public=True))
    await session.commit()
    repo = MasterRepository(session)
    items = await repo.list_public()
    slugs = [m.slug for m in items]
    assert "a-0001" in slugs
    assert "d-0001" in slugs
    assert "b-0001" not in slugs
    assert "c-0001" not in slugs


@pytest.mark.asyncio
async def test_set_blocked_toggle(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="a-0001")
    session.add(m)
    await session.commit()
    repo = MasterRepository(session)
    await repo.set_blocked(m.id, blocked=True)
    await session.commit()
    await session.refresh(m)
    assert m.blocked_at is not None

    await repo.set_blocked(m.id, blocked=False)
    await session.commit()
    await session.refresh(m)
    assert m.blocked_at is None


@pytest.mark.asyncio
async def test_update_slug_ok(session: AsyncSession) -> None:
    m = Master(tg_id=1, name="A", slug="a-0001")
    session.add(m)
    await session.commit()
    repo = MasterRepository(session)
    await repo.update_slug(m.id, "new-slug")
    await session.commit()
    await session.refresh(m)
    assert m.slug == "new-slug"


@pytest.mark.asyncio
async def test_update_slug_collision(session: AsyncSession) -> None:
    from sqlalchemy.exc import IntegrityError

    m1 = Master(tg_id=1, name="A", slug="a-0001")
    m2 = Master(tg_id=2, name="B", slug="b-0001")
    session.add_all([m1, m2])
    await session.commit()
    repo = MasterRepository(session)
    await repo.update_slug(m2.id, "a-0001")
    with pytest.raises(IntegrityError):
        await session.commit()
