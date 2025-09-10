import logging
from litestar import Controller, get
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from app.models import ProgramList, DecodedCursorPagination
from app.database import DatabaseService, ProgramListPagination

logger = logging.getLogger(__name__)


class ProgramsController(Controller):
    path = "/programs"
    tags = ["Programs"]

    @get(
        path="/",
        description="Get all programs",
        summary="Get all programs",
    )
    async def get_programs(
        self,
        db_service: DatabaseService,
        decoded_cursor_pagination: DecodedCursorPagination,
    ) -> ProgramList:
        try:
            return await db_service.get_programs(
                source=None,
                pagination=ProgramListPagination(
                    size=decoded_cursor_pagination.size,
                    after_title=decoded_cursor_pagination.cursor.get("title"),
                    after_uri=decoded_cursor_pagination.cursor.get("uri"),
                ),
            )
        except Exception as e:
            logger.exception(e)

            raise HTTPException(
                detail="Internal server error: An unexpected error occurred",
                status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )
