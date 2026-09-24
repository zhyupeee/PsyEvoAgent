"""Reject accidental use of a development database before any PostgreSQL test runs."""

import os

import pytest
from pydantic import SecretStr

from app.config import Settings


@pytest.fixture(autouse=True)
def isolated_postgres(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("postgres"):
        Settings(environment="test", database_url=SecretStr(os.environ["PSYEVO_TEST_DATABASE_URL"]))
