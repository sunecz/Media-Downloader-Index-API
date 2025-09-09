import logging
from litestar import Controller, get
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR
from app.models import ProgramList, Pagination
from app.database import DatabaseService

logger = logging.getLogger(__name__)

SUPPORTED_WEBSITES = ["iprima"]


class WebsitesController(Controller):
    path = "/websites"
    tags = ["Websites"]

    @get(
        path="/",
        description="Get all supported websites",
        summary="Get all supported websites",
    )
    async def get_all_websites(
        self,
    ) -> list[str]:
        return SUPPORTED_WEBSITES

    @get(
        path="/{website:str}/programs",
        description="Get programs by website",
        summary="Get programs by website",
    )
    async def get_programs_by_website(
        self,
        website: str,
        db_service: DatabaseService,
        pagination: Pagination,
    ) -> ProgramList:
        try:
            if not website or website not in SUPPORTED_WEBSITES:
                raise HTTPException(
                    detail=f"Invalid website parameter. Website must be one of: {', '.join(SUPPORTED_WEBSITES)}",
                    status_code=HTTP_400_BAD_REQUEST
                )

            programs, total_count = await db_service.get_programs(
                source=website,
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
