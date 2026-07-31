"""Engine and session construction.

This is the only module that knows a database URL. Everything above `core` goes through
repositories, which is what makes the PostgreSQL move a configuration change.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel.ext.asyncio.session import AsyncSession

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///./hub.db"

# Layers above core annotate against these names rather than importing SQLAlchemy themselves. The
# aliases are the seam: if the session type changes, it changes here.
DatabaseEngine = AsyncEngine
DatabaseSession = AsyncSession
SessionFactory = async_sessionmaker[AsyncSession]


def create_engine(url: str = DEFAULT_DATABASE_URL) -> AsyncEngine:
    return create_async_engine(url, future=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Commit on success, roll back on failure."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
