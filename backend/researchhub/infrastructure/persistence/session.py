"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from researchhub.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=settings.db_pool_pre_ping,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout_seconds,
    pool_recycle=settings.db_pool_recycle_seconds,
    connect_args={
        "server_settings": {
            "statement_timeout": str(settings.db_statement_timeout_ms),
            "lock_timeout": str(settings.db_lock_timeout_ms),
            "idle_in_transaction_session_timeout": str(settings.db_idle_transaction_timeout_ms),
            "application_name": settings.app_name,
        },
        **({"statement_cache_size": 0} if settings.db_use_pgbouncer else {}),
    },
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Backward-compatible alias in case other files import SessionLocal.
SessionLocal = async_session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a unit-of-work scoped async database session."""

    async with async_session_factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
