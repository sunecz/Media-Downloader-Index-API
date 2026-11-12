from dataclasses import dataclass
import logging
from sqlalchemy import Select, Text, bindparam, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncConnection
from app.db.models import Program, Source
from app.models import (
    CursorPaginationResult,
    Program as ProgramModel,
    ProgramCursor,
    ProgramList,
)
from app.utils import encode_cursor

logger = logging.getLogger(__name__)


@dataclass
class ProgramListPagination:
    size: int
    after: ProgramCursor | None = None


# Titled only, pagination orders by title
_listed = (Program.active.is_(True), Program.title.is_not(None))


class ProgramsService:

    def _query_get_programs(
        self,
        source_id: int | None,
        pagination: ProgramListPagination | None,
    ) -> Select:
        # Plain columns match the title indexes; lower()/COLLATE would not
        query = (
            select(Program.uri, Program.title, Program.type, Source.name)
            .join(Source, Source.id == Program.source_id)
            .where(*_listed)
            .order_by(Program.title, Program.uri)
        )

        if source_id is not None:
            query = query.where(Program.source_id == source_id)

        if pagination is not None:
            if (after := pagination.after) is not None:
                query = query.where(
                    tuple_(Program.title, Program.uri) > tuple_(
                        bindparam("after_title", after.title, Text),
                        bindparam("after_uri", after.uri, Text),
                    )
                )

            # +1 to check if there are more items after the true limit
            query = query.limit(pagination.size + 1)

        return query

    async def _get_programs_total(
        self,
        conn: AsyncConnection,
        source_id: int | None,
    ) -> int:
        query = select(func.count()).select_from(Program).where(*_listed)

        if source_id is not None:
            query = query.where(Program.source_id == source_id)

        return int(await conn.scalar(query) or 0)

    async def get_programs(
        self,
        conn: AsyncConnection,
        source_id: int | None = None,
        pagination: ProgramListPagination | None = None,
    ) -> ProgramList:
        result = await conn.execute(
            self._query_get_programs(source_id, pagination)
        )

        programs = [
            ProgramModel(source=name, uri=uri, title=title, type=type_)
            for uri, title, type_, name in result
        ]

        total_count = len(programs)
        size = total_count
        next_cursor = None

        if pagination is not None:
            list_size = total_count
            size = pagination.size
            total_count = await self._get_programs_total(conn, source_id)

            if list_size > size:
                programs = programs[:size]
                last_program = programs[-1]
                next_cursor = encode_cursor(ProgramCursor(
                    title=last_program.title,
                    uri=last_program.uri,
                ))

        return ProgramList(
            programs=programs,
            total=total_count,
            pagination=CursorPaginationResult(
                size=size,
                next_cursor=next_cursor,
            )
        )
