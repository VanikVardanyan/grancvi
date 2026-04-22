from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.invites import InviteRepository


@pytest.mark.asyncio
async def test_create_invite(session: AsyncSession) -> None:
    repo = InviteRepository(session)
    invite = await repo.create(
        code="TEST-0001",
        created_by_tg_id=111,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    await session.commit()
    assert invite.code == "TEST-0001"
    assert invite.used_at is None


@pytest.mark.asyncio
async def test_by_code_found(session: AsyncSession) -> None:
    repo = InviteRepository(session)
    await repo.create(
        code="FIND-0001",
        created_by_tg_id=111,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    await session.commit()
    found = await repo.by_code("FIND-0001")
    assert found is not None
    assert found.code == "FIND-0001"


@pytest.mark.asyncio
async def test_by_code_not_found(session: AsyncSession) -> None:
    repo = InviteRepository(session)
    assert await repo.by_code("MISSING") is None


@pytest.mark.asyncio
async def test_list_by_creator_desc(session: AsyncSession) -> None:
    repo = InviteRepository(session)
    for i in range(3):
        await repo.create(
            code=f"CODE-{i:04d}",
            created_by_tg_id=777,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    await session.commit()
    items = await repo.list_by_creator(777)
    assert len(items) == 3
