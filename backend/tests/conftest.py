import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_db
from app.main import create_app

# Each test gets a fresh in-memory SQLite DB via StaticPool so the
# single connection is shared across the async session (in-memory
# sqlite is otherwise per-connection, which breaks under async).
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    # The deployment worker runs as a detached asyncio task, outside
    # FastAPI's request-scoped DI — it needs its own session-factory
    # override to land in this test's isolated DB instead of the app's
    # real one. See app/services/deployment_worker.py.
    from app.services import deployment_worker

    original_factory = deployment_worker._session_factory
    deployment_worker.set_session_factory(session_maker)

    async with session_maker() as session:
        yield session

    deployment_worker.set_session_factory(original_factory)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def auth_headers(client: AsyncClient, username: str) -> dict:
    resp = await client.post(
        "/auth/token", data={"username": username, "password": "x"}
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
