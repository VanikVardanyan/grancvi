from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.services.moderation import ModerationService


@pytest.mark.asyncio
async def test_block_sets_blocked_at_and_rejects_pending(
    session: AsyncSession,
) -> None:
    m = Master(tg_id=1, name="A", slug="a-0001")
    session.add(m)
    await session.flush()
    svc = Service(master_id=m.id, name="cut", duration_min=30)
    cli = Client(master_id=m.id, name="C", phone="+111", tg_id=999)
    session.add_all([svc, cli])
    await session.flush()
    now = datetime.now(timezone.utc)
    appt = Appointment(
        master_id=m.id, client_id=cli.id, service_id=svc.id,
        start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=2),
        status="pending", source="client_request",
    )
    session.add(appt)
    await session.commit()

    service = ModerationService(session)
    result = await service.block_master(m.id)
    await session.commit()

    await session.refresh(m)
    await session.refresh(appt)
    assert m.blocked_at is not None
    assert appt.status == "rejected"
    assert len(result.rejected) == 1
    assert result.rejected[0].client_tg_id == 999


@pytest.mark.asyncio
async def test_unblock_clears_blocked_at(session: AsyncSession) -> None:
    m = Master(
        tg_id=1, name="A", slug="a-0001",
        blocked_at=datetime.now(timezone.utc),
    )
    session.add(m)
    await session.commit()
    svc = ModerationService(session)
    await svc.unblock_master(m.id)
    await session.commit()
    await session.refresh(m)
    assert m.blocked_at is None
