"""Shared test fixtures: in-memory SQLite DB + an ASGI client with the DB
dependency overridden and Redis stubbed, so the suite needs no external
services.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register tables on Base.metadata)
from app.database.base import Base


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(session_factory, monkeypatch):
    from app.core import redis as redis_helpers
    from app.database import get_session
    from app.main import app

    async def _override_session():
        async with session_factory() as session:
            yield session
            await session.commit()

    async def _fake_ping():
        return True

    app.dependency_overrides[get_session] = _override_session
    monkeypatch.setattr(redis_helpers, "ping", _fake_ping)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
