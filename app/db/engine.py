from collections.abc import AsyncGenerator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine
from app.config import config
from app.db.models import DatasetMeta

# Reads only: AUTOCOMMIT skips BEGIN/ROLLBACK round trips
engine = create_async_engine(
    config.database_url,
    pool_size=config.db_pool_size,
    max_overflow=config.db_max_overflow,
    pool_pre_ping=True,
    isolation_level="AUTOCOMMIT",
)


async def start_db() -> None:
    # Fail fast on a bad URL
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def stop_db() -> None:
    await engine.dispose()


async def get_db_connection() -> AsyncGenerator[AsyncConnection, None]:
    async with engine.connect() as conn:
        yield conn


_query_dataset_version = select(DatasetMeta.version).where(DatasetMeta.id == 1)


async def get_dataset_version(conn: AsyncConnection) -> int | None:
    return await conn.scalar(_query_dataset_version)
