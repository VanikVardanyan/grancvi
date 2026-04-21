from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master
from src.repositories.clients import ClientRepository


async def _seed(session: AsyncSession) -> tuple[Master, Client]:
    master = Master(tg_id=7100, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    client = Client(master_id=master.id, name="A", phone="+37499000111")
    session.add(client)
    await session.flush()
    return master, client


@pytest.mark.asyncio
async def test_update_notes_sets_value(session: AsyncSession) -> None:
    _, client = await _seed(session)
    repo = ClientRepository(session)
    await repo.update_notes(client.id, "аллергия на латекс")
    await session.flush()
    reloaded = await repo.get(client.id)
    assert reloaded is not None
    assert reloaded.notes == "аллергия на латекс"


@pytest.mark.asyncio
async def test_update_notes_clears_on_none(session: AsyncSession) -> None:
    _, client = await _seed(session)
    client.notes = "old"
    await session.flush()

    repo = ClientRepository(session)
    await repo.update_notes(client.id, None)
    await session.flush()
    reloaded = await repo.get(client.id)
    assert reloaded is not None
    assert reloaded.notes is None


@pytest.mark.asyncio
async def test_update_notes_empty_string_clears(session: AsyncSession) -> None:
    _, client = await _seed(session)
    client.notes = "old"
    await session.flush()

    repo = ClientRepository(session)
    await repo.update_notes(client.id, "")
    await session.flush()
    reloaded = await repo.get(client.id)
    assert reloaded is not None
    assert reloaded.notes is None


@pytest.mark.asyncio
async def test_update_notes_noop_on_unknown_client(session: AsyncSession) -> None:
    from uuid import uuid4

    repo = ClientRepository(session)
    # Should not raise.
    await repo.update_notes(uuid4(), "x")
