"""FastAPI application factory."""

from __future__ import annotations

import contextlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes_health import router as health_router
from app.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import RequestContextMiddleware, configure_logging, get_logger
from app.core.redis import close_redis
from app.database import dispose_engine

_STATIC_DIR = Path(__file__).parent / "static"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("app")
    log.info("startup", app=settings.app_name, environment=settings.environment)
    yield
    await dispose_engine()
    await close_redis()
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    # API routers
    app.include_router(health_router)

    # Web dashboard + additional API routers are mounted here as they are built.
    _mount_optional_routers(app)

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app


def _mount_optional_routers(app: FastAPI) -> None:
    """Include routers that are added in later build phases, if present."""
    try:
        from app.api.routes_trends import router as trends_router
        from app.api.routes_titles import router as titles_router
        from app.api.routes_scripts import router as scripts_router
        from app.api.routes_pipeline import router as pipeline_router

        app.include_router(trends_router)
        app.include_router(titles_router)
        app.include_router(scripts_router)
        app.include_router(pipeline_router)
    except ImportError:
        pass

    try:
        from app.api.routes_web import router as web_router

        app.include_router(web_router)
    except ImportError:
        pass


app = create_app()
