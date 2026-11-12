import logging
import logging.config
from litestar import Litestar
from litestar.di import Provide
from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.logging import LoggingConfig
from litestar.config.cors import CORSConfig
from app.logging_config import LOGGING_CONFIG
from app.config import config
from app.controllers import ProgramsController, WebsitesController
from app.dependencies import (
    get_cursor_pagination,
    get_decoded_cursor_pagination,
    get_programs_service,
    get_sources_service,
)
from app.db import get_db_connection, start_db, stop_db
from app.cache import start_cache, stop_cache

logging.config.dictConfig(LOGGING_CONFIG)


def create_app() -> Litestar:
    logging_config = LoggingConfig(
        root={'level': 'INFO', 'handlers': ['console']},
        formatters={
            'console': {
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            },
        },
        log_exceptions='always',
    )

    openapi_config: OpenAPIConfig = OpenAPIConfig(
        title=config.api_title,
        version=config.api_version,
        description=config.api_description,
        path="/docs",
        servers=[],
        render_plugins=[
            SwaggerRenderPlugin(path="/docs"),
        ],
    )

    cors_config = CORSConfig(
        allow_origins=["*"],
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    return Litestar(
        cors_config=cors_config,
        logging_config=logging_config,
        openapi_config=openapi_config,
        route_handlers=[
            ProgramsController,
            WebsitesController,
        ],
        dependencies={
            "db": Provide(get_db_connection),
            "programs_service": Provide(get_programs_service),
            "sources_service": Provide(get_sources_service),
            "cursor_pagination": Provide(get_cursor_pagination),
            "decoded_cursor_pagination": Provide(get_decoded_cursor_pagination),
        },
        on_startup=[start_db, start_cache],
        on_shutdown=[stop_cache, stop_db],
    )


app: Litestar = create_app()
