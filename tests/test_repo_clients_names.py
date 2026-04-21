from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Client, Master
from src.repositories.clients import ClientRepository


async def _seed(session: AsyncSession) -> tuple[Master, list[Client]]:
    master = Master(tg_id=7200, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    clients = [
        Client(master_id=master.id, name="Анна", phone="+37499000001"),
        Client(master_id=master.id, name="Иван", phone="+37499000002"),
        Client(master_id=master.id, name="Ольга", phone="+37499000003"),
    ]
    session.add_all(clients)
    await session.flush()
    return master, clients


@pytest.mark.asyncio
async def test_get_names_by_ids_empty_input(session: AsyncSession) -> None:
    await _seed(session)
    repo = ClientRepository(session)
    result = await repo.get_names_by_ids([])
    assert result == {}


@pytest.mark.asyncio
async def test_get_names_by_ids_subset(session: AsyncSession) -> None:
    _, clients = await _seed(session)
    repo = ClientRepository(session)
    ids = [clients[0].id, clients[2].id]
    result = await repo.get_names_by_ids(ids)
    assert result == {clients[0].id: "Анна", clients[2].id: "Ольга"}


@pytest.mark.asyncio
async def test_get_names_by_ids_unknown_id_ignored(session: AsyncSession) -> None:
    _, clients = await _seed(session)
    repo = ClientRepository(session)
    missing = uuid4()
    result = await repo.get_names_by_ids([clients[0].id, missing])
    assert result == {clients[0].id: "Анна"}
    assert missing not in result
