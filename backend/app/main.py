"""API factory: importing this module creates neither clients nor consumers."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api import APIError, router
from app.config import Settings, load_settings
from app.database import make_engine
from app.deletion import router as deletion_router
from app.history import router as history_router
from app.jobs import router as jobs_router
from app.mail import Mailer, SMTPMailer
from app.model_settings_api import router as model_settings_router
from app.models import opaque_id
from app.pages import router as pages_router
from app.records import router as records_router
from app.run_stream import Connections
from app.run_stream import router as stream_router
from app.runs import router as runs_router

logger = logging.getLogger("uvicorn.error")


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    stage: Literal["S1-STEP02"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = app.state.settings
    app.state.engine = (
        make_engine(settings.database_url.get_secret_value()) if settings.database_url else None
    )
    config_task: asyncio.Task[None] | None = None
    if (
        settings.environment == "development"
        and settings.support_mode == "live"
        and settings.provider_config_file
    ):
        from app.provider_config import official_settings

        async def refresh_config() -> None:
            while True:
                try:
                    await asyncio.to_thread(official_settings, settings)
                except ValueError:
                    pass  # A malformed save keeps the last valid in-memory configuration.
                await asyncio.sleep(0.5)

        config_task = asyncio.create_task(refresh_config())
    logger.info("api.started")
    try:
        yield
    finally:
        if config_task is not None:
            config_task.cancel()
            await asyncio.gather(config_task, return_exceptions=True)
        if app.state.engine is not None:
            app.state.engine.dispose()
        logger.info("api.stopped")


def create_app(settings: Settings | None = None, mailer: Mailer | None = None) -> FastAPI:
    application = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
    application.state.settings = settings if settings is not None else load_settings()
    application.state.engine = None
    application.state.mailer = mailer or SMTPMailer(application.state.settings)
    application.include_router(router)
    application.include_router(model_settings_router)
    application.include_router(runs_router)
    application.include_router(stream_router)
    application.include_router(pages_router)
    application.include_router(records_router)
    application.include_router(deletion_router)
    application.include_router(history_router)
    application.include_router(jobs_router)
    application.state.run_connections = Connections()

    @application.middleware("http")
    async def private_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = opaque_id()
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    async def error_response(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, APIError):
            status, code = exc.status, exc.code
        elif isinstance(exc, RequestValidationError):
            status, code = 422, "invalid_request"
        elif isinstance(exc, HTTPException):
            status, code = (
                exc.status_code,
                "not_found" if exc.status_code == 404 else "request_rejected",
            )
        else:
            status, code = 503, "storage_unavailable"
        return JSONResponse(
            status_code=status,
            content={
                "code": code,
                "message": "请求未完成，请核对状态后再试。",
                "request_id": request.state.request_id,
                "retryable": status in {429, 503},
            },
        )

    for exception in (APIError, RequestValidationError, HTTPException, SQLAlchemyError):
        application.add_exception_handler(exception, error_response)

    @application.get("/api/v1/health", response_model=Health)
    async def health() -> Health:
        return Health(status="ok", stage="S1-STEP02")

    return application
