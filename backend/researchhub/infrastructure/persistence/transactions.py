"""Transaction helpers for application services."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def transaction(session: AsyncSession) -> AsyncIterator[None]:
    """Run a service operation inside a database transaction.

    If the caller already owns an open transaction, this helper reuses it. This
    keeps service methods composable while still giving top-level API calls
    atomic commit/rollback semantics.
    """

    if session.in_transaction():
        yield
        return
    async with session.begin():
        yield
