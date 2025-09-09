import logging
from litestar import Controller, get
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from app.models import ProgramList, Pagination
from app.database import DatabaseService

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
        pagination: Pagination,
    ) -> ProgramList:
        try:
            programs, total_count = await db_service.get_programs(
                source=None,
                page=pagination.page,
                size=pagination.size
            )

            return ProgramList(
                programs=programs,
                total=total_count,
                pagination=pagination
            )
        except Exception as e:
            logger.exception(e)

            raise HTTPException(
                detail="Internal server error: An unexpected error occurred",
                status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )
