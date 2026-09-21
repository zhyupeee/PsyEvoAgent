"""Read only explicitly supported process variables; never auto-load .env files."""

import os
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: Literal["development", "test"] = "development"


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if environ is None else environ
    return Settings.model_validate({"environment": source.get("PSYEVO_ENV", "development")})
