from fastapi import FastAPI

from app.api.v1 import API_PREFIX, router
from app.config import get_settings
from app.logging_setup import setup_logging


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(
        title="Mail Sorter",
        description="Sorter mailowy. Lokalny model językowy "
        "klasyfikuje treść, agent przekazuje ją mailem do właściwego działu.",
        version="0.1.0",
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        redoc_url=None,
    )
    app.include_router(router)
    return app


app = create_app()
