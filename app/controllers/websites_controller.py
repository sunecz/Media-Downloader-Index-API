import logging
from litestar import Controller, get
from litestar.exceptions import HTTPException
from litestar.status_codes import HTTP_400_BAD_REQUEST, HTTP_500_INTERNAL_SERVER_ERROR
from sqlalchemy.ext.asyncio import AsyncConnection
from app.cache import CacheMiddleware
from app.models import ProgramList, DecodedCursorPagination
from app.services import ProgramsService, SourcesService
from app.services.programs_service import ProgramListPagination

logger = logging.getLogger(__name__)


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
        db: AsyncConnection,
        sources_service: SourcesService,
    ) -> list[str]:
        try:
            return await sources_service.list_names(db)
        except Exception as e:
            logger.exception(e)

            raise HTTPException(
                detail="Internal server error: An unexpected error occurred",
                status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )

    @get(
        path="/{website:str}/programs",
        description="Get programs by website",
        summary="Get programs by website",
        middleware=[CacheMiddleware()],
    )
    async def get_programs_by_website(
        self,
        website: str,
        db: AsyncConnection,
        programs_service: ProgramsService,
        sources_service: SourcesService,
        decoded_cursor_pagination: DecodedCursorPagination,
    ) -> ProgramList:
        try:
            source_id = await sources_service.resolve_id(db, website)

            if source_id is None:
                websites = await sources_service.list_names(db)
                raise HTTPException(
                    detail=f"Invalid website parameter. Website must be one of: {', '.join(websites)}",
                    status_code=HTTP_400_BAD_REQUEST
                )

            return await programs_service.get_programs(
                db,
                source_id=source_id,
                pagination=ProgramListPagination(
                    size=decoded_cursor_pagination.size,
                    after=decoded_cursor_pagination.cursor,
                ),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(e)

            raise HTTPException(
                detail="Internal server error: An unexpected error occurred",
                status_code=HTTP_500_INTERNAL_SERVER_ERROR
            )
