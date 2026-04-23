from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Invite, Master, Salon


@pytest.mark.asyncio
async def test_salon_can_be_created_with_minimum_fields(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=12345, name="Test Salon", slug="test-salon")
    session.add(salon)
    await session.flush()
    await session.commit()
    await session.refresh(salon)
    assert salon.id is not None
    assert salon.is_public is True
    assert salon.logo_file_id is None


@pytest.mark.asyncio
async def test_master_can_be_linked_to_salon(session: AsyncSession) -> None:
    salon = Salon(owner_tg_id=111, name="S", slug="s-1")
    session.add(salon)
    await session.flush()
    master = Master(tg_id=222, name="M", slug="m-1", salon_id=salon.id)
    session.add(master)
    await session.flush()
    await session.commit()
    await session.refresh(master)
    assert master.salon_id == salon.id


@pytest.mark.asyncio
async def test_invite_has_kind_and_optional_salon(session: AsyncSession) -> None:
    from datetime import UTC, datetime, timedelta

    expires = datetime.now(UTC) + timedelta(days=7)
    inv = Invite(code="abc123", created_by_tg_id=999, expires_at=expires, kind="master")
    session.add(inv)
    await session.flush()
    await session.commit()
    await session.refresh(inv)
    assert inv.kind == "master"
    assert inv.salon_id is None
