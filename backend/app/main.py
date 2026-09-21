"""API factory: importing this module creates neither clients nor consumers."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from app.config import Settings, load_settings

logger = logging.getLogger("uvicorn.error")


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    stage: Literal["S1-STEP02"]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # No HTTP/DB resource is needed yet; add real resources here when consumed.
    logger.info("api.started")
    try:
        yield
    finally:
        logger.info("api.stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    application = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
    application.state.settings = settings if settings is not None else load_settings()

    @application.get("/api/v1/health", response_model=Health)
    async def health() -> Health:
        return Health(status="ok", stage="S1-STEP02")

    return application
