from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Master, Service
from src.repositories.services import ServiceRepository


async def _seed(session: AsyncSession) -> tuple[Master, list[Service]]:
    master = Master(tg_id=7300, name="M", timezone="Asia/Yerevan")
    session.add(master)
    await session.flush()
    services = [
        Service(master_id=master.id, name="Стрижка", duration_min=60),
        Service(master_id=master.id, name="Окрашивание", duration_min=120),
        Service(master_id=master.id, name="Укладка", duration_min=30),
    ]
    session.add_all(services)
    await session.flush()
    return master, services


@pytest.mark.asyncio
async def test_get_names_by_ids_empty_input(session: AsyncSession) -> None:
    await _seed(session)
    repo = ServiceRepository(session)
    result = await repo.get_names_by_ids([])
    assert result == {}


@pytest.mark.asyncio
async def test_get_names_by_ids_subset(session: AsyncSession) -> None:
    _, services = await _seed(session)
    repo = ServiceRepository(session)
    ids = [services[0].id, services[2].id]
    result = await repo.get_names_by_ids(ids)
    assert result == {services[0].id: "Стрижка", services[2].id: "Укладка"}


@pytest.mark.asyncio
async def test_get_names_by_ids_unknown_id_ignored(session: AsyncSession) -> None:
    _, services = await _seed(session)
    repo = ServiceRepository(session)
    missing = uuid4()
    result = await repo.get_names_by_ids([services[0].id, missing])
    assert result == {services[0].id: "Стрижка"}
    assert missing not in result
