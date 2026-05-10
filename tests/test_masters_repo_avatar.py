from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.masters import MasterRepository


@pytest.mark.asyncio
async def test_set_avatar_uploaded_at_sets_and_clears(session: AsyncSession) -> None:
    repo = MasterRepository(session)
    master = await repo.create(tg_id=12345, name="A")
    master_id = master.id

    ts = datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC)
    await repo.set_avatar_uploaded_at(master_id, ts)
    await session.flush()
    session.expire(master)
    refreshed = await repo.by_id(master_id)
    assert refreshed is not None
    assert refreshed.avatar_uploaded_at == ts

    await repo.set_avatar_uploaded_at(master_id, None)
    await session.flush()
    session.expire(master)
    refreshed = await repo.by_id(master_id)
    assert refreshed is not None
    assert refreshed.avatar_uploaded_at is None
