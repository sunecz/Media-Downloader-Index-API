from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection
from app.db.models import Source


class SourcesService:

    async def list_names(self, conn: AsyncConnection) -> list[str]:
        result = await conn.scalars(select(Source.name).order_by(Source.name))
        return list(result)

    async def resolve_id(self, conn: AsyncConnection, name: str) -> int | None:
        return await conn.scalar(select(Source.id).where(Source.name == name))
