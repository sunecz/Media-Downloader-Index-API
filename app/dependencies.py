from app.config import config
from app.database import DatabaseService
from app.models import Pagination


async def get_db_service() -> DatabaseService:
    return DatabaseService()


async def get_pagination(
    page: int | None = None,
    size: int | None = None,
) -> Pagination:
    if page is None or page < 1:
        page = 1

    if size is None or size < 1:
        size = config.default_page_size

    if size > config.max_page_size:
        size = config.max_page_size

    return Pagination(page=page, size=size)
