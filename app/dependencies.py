import msgspec
from app.config import config
from app.services import ProgramsService, SourcesService
from app.models import CursorPagination, DecodedCursorPagination, ProgramCursor
from app.utils import decode_cursor


async def get_programs_service() -> ProgramsService:
    return ProgramsService()


async def get_sources_service() -> SourcesService:
    return SourcesService()


async def get_cursor_pagination(
    cursor: str | None = None,
    size: int | None = None,
) -> CursorPagination:
    return CursorPagination(cursor=cursor, size=size)


async def get_decoded_cursor_pagination(
    cursor_pagination: CursorPagination | None = None,
) -> DecodedCursorPagination:
    if cursor_pagination is None:
        return DecodedCursorPagination(
            cursor=None,
            size=config.default_page_size,
        )

    cursor = cursor_pagination.cursor
    size = cursor_pagination.size
    decoded_cursor: ProgramCursor | None = None

    if cursor:
        try:
            decoded_cursor = decode_cursor(cursor, ProgramCursor)
        except (ValueError, msgspec.DecodeError):
            pass  # Malformed, start from the first page

    if size is None or size < 1:
        size = config.default_page_size

    if size > config.max_page_size:
        size = config.max_page_size

    return DecodedCursorPagination(cursor=decoded_cursor, size=size)
