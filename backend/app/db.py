from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


# echo=False in all environments; SQL logging is opt-in via log level,
# not baked into engine construction, to keep prod logs clean.
engine = create_async_engine(settings.database_url, echo=False, future=True)

AsyncSessionLocal = async_sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped session.

    Commit/rollback is the caller's (service layer's) responsibility so
    that a service can compose multiple repository calls into a single
    transaction where needed (see DeploymentService).
    """
    async with AsyncSessionLocal() as session:
        yield session
