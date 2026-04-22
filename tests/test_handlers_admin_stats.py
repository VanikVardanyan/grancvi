from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Appointment, Client, Master, Service
from src.handlers.admin.stats import cmd_admin_stats


@pytest.mark.asyncio
async def test_stats_counts(session: AsyncSession) -> None:
    m1 = Master(tg_id=1, name="A", slug="a-0001")
    m2 = Master(
        tg_id=2,
        name="B",
        slug="b-0001",
        blocked_at=datetime.now(UTC),
    )
    session.add_all([m1, m2])
    await session.flush()
    svc = Service(master_id=m1.id, name="cut", duration_min=30)
    cli = Client(master_id=m1.id, name="C", phone="+111", tg_id=999)
    session.add_all([svc, cli])
    await session.flush()

    now = datetime.now(UTC)
    session.add(
        Appointment(
            master_id=m1.id,
            client_id=cli.id,
            service_id=svc.id,
            start_at=now,
            end_at=now + timedelta(hours=1),
            status="confirmed",
            source="client_request",
            created_at=now - timedelta(days=2),
        )
    )
    session.add(
        Appointment(
            master_id=m1.id,
            client_id=cli.id,
            service_id=svc.id,
            start_at=now + timedelta(hours=2),
            end_at=now + timedelta(hours=3),
            status="confirmed",
            source="client_request",
            created_at=now - timedelta(days=20),
        )
    )
    await session.commit()

    message = AsyncMock()
    await cmd_admin_stats(message=message, session=session)
    text = message.answer.await_args[0][0]
    assert "1" in text  # active masters
    assert "1" in text  # blocked
