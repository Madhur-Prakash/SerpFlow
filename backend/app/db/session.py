"""Async engine, session factory, and the per-transaction RLS tenant guard."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _async_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://") or url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _async_url(settings.database_url),
            echo=settings.database_echo,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def set_tenant(session: AsyncSession, org_id: str | None) -> None:
    """Scope the transaction for PostgreSQL row-level security (section 36).

    ``SET LOCAL`` is transaction-scoped, so this must be issued inside the
    transaction that will run the queries. Application-level guards in
    ``app/api/deps.py`` enforce the same boundary independently; RLS is the
    backstop, not the only check.
    """
    if org_id:
        await session.execute(
            text("SELECT set_config('app.current_org', :org, true)"), {"org": org_id}
        )
    else:
        await session.execute(text("SELECT set_config('app.current_org', '', true)"))


@asynccontextmanager
async def session_scope(org_id: str | None = None) -> AsyncIterator[AsyncSession]:
    """Transactional scope for workers, scripts and the CLI."""
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            if org_id:
                await set_tenant(session, org_id)
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. The tenant guard is applied by ``deps.get_principal``
    once the principal (and therefore the org) is known."""
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def ping() -> tuple[bool, str | None]:
    """Readiness probe. Returns ``(ok, detail)`` so /readyz can say *why* it is
    failing rather than only that it is."""
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        return False, type(exc).__name__ + ": " + str(exc)[:200]


__all__ = [
    "dispose_engine",
    "get_db",
    "get_engine",
    "get_sessionmaker",
    "ping",
    "session_scope",
    "set_tenant",
]
