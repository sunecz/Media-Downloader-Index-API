import binascii
import msgspec
from app.config import config
from app.database import DatabaseService
from app.models import CursorPagination, DecodedCursorPagination
from app.utils import decode_cursor


async def get_db_service() -> DatabaseService:
    return DatabaseService()


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
            cursor={},
            size=config.default_page_size,
        )

    cursor = cursor_pagination.cursor
    size = cursor_pagination.size
    decoded_cursor: dict = {}

    if cursor and isinstance(cursor, str):
        try:
            decoded_cursor = decode_cursor(cursor)
        except (binascii.Error, msgspec.DecodeError):
            pass  # Silently ignore

    if size is None or size < 1:
        size = config.default_page_size

    if size > config.max_page_size:
        size = config.max_page_size

    return DecodedCursorPagination(cursor=decoded_cursor, size=size)
