import logging
from litestar import Controller, get
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR
from app.cache import CacheMiddleware
from app.models import ProgramList, DecodedCursorPagination
from app.services import ProgramsService
from app.services.programs_service import ProgramListPagination
from app.utils import normalize_str

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
        middleware=[CacheMiddleware()],
    )
    async def get_programs_by_website(
        self,
        website: str,
        programs_service: ProgramsService,
        decoded_cursor_pagination: DecodedCursorPagination,
    ) -> ProgramList:
        try:
            if not website or website not in SUPPORTED_WEBSITES:
                raise HTTPException(
                    detail=f"Invalid website parameter. Website must be one of: {', '.join(SUPPORTED_WEBSITES)}",
                    status_code=HTTP_400_BAD_REQUEST
                )

            return await programs_service.get_programs(
                source=website,
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
