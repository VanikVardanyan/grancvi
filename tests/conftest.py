from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.db import models  # noqa: F401  # ensure metadata is populated
from src.db.base import Base

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://botik:botik@localhost:5432/botik_test",
)


@pytest_asyncio.fixture(scope="session")
async def _test_engine() -> AsyncGenerator[AsyncEngine, None]:
    admin_engine = create_async_engine(
        "postgresql+asyncpg://botik:botik@localhost:5432/botik",
        isolation_level="AUTOCOMMIT",
    )
    async with admin_engine.connect() as conn:
        await conn.exec_driver_sql("DROP DATABASE IF EXISTS botik_test")
        await conn.exec_driver_sql("CREATE DATABASE botik_test")
    await admin_engine.dispose()

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables(_test_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Clean all data between tests so tg_id unique constraints don't collide."""
    yield
    async with _test_engine.begin() as conn:
        table_names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        if table_names:
            await conn.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture
async def session(_test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    maker = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s


@pytest.fixture
def session_maker(_test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)
