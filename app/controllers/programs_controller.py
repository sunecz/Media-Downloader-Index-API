import logging
from litestar import Controller, get
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from sqlalchemy.ext.asyncio import AsyncConnection
from app.models import ProgramList, DecodedCursorPagination
from app.services import ProgramsService
from app.services.programs_service import ProgramListPagination
from app.cache import CacheMiddleware

logger = logging.getLogger(__name__)


class ProgramsController(Controller):
    path = "/programs"
    tags = ["Programs"]

    @get(
        path="/",
        description="Get active programs available on demand, from all websites",
        summary="Get available programs",
        middleware=[CacheMiddleware()],
    )
    async def get_programs(
        self,
        db: AsyncConnection,
        programs_service: ProgramsService,
        decoded_cursor_pagination: DecodedCursorPagination,
    ) -> ProgramList:
        try:
            return await programs_service.get_programs(
                db,
                source_id=None,
                pagination=ProgramListPagination(
                    size=decoded_cursor_pagination.size,
                    after=decoded_cursor_pagination.cursor,
                ),
            )
        except Exception as e:
            logger.exception(e)

            raise HTTPException(
                detail="Internal server error: An unexpected error occurred",
                status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )
