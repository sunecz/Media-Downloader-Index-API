import logging
from litestar import Controller, get
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from app.models import ProgramList, DecodedCursorPagination
from app.services import ProgramsService
from app.services.programs_service import ProgramListPagination
from app.cache import CacheMiddleware
from app.utils import normalize_str

logger = logging.getLogger(__name__)


class ProgramsController(Controller):
    path = "/programs"
    tags = ["Programs"]

    @get(
        path="/",
        description="Get all programs",
        summary="Get all programs",
        middleware=[CacheMiddleware()],
    )
    async def get_programs(
        self,
        programs_service: ProgramsService,
        decoded_cursor_pagination: DecodedCursorPagination,
    ) -> ProgramList:
        try:
            return await programs_service.get_programs(
                source=None,
                pagination=ProgramListPagination(
                    size=decoded_cursor_pagination.size,
                    after_title=normalize_str(
                        decoded_cursor_pagination.cursor.get("title")
                    ),
                    after_uri=decoded_cursor_pagination.cursor.get("uri"),
                ),
            )
        except Exception as e:
            logger.exception(e)

            raise HTTPException(
                detail="Internal server error: An unexpected error occurred",
                status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )
