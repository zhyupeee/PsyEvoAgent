"""Configuration-only checks; no database connection or paid provider calls."""

import pytest
from pydantic import ValidationError

from app.config import load_settings


def config(environment: str, host: str, database: str, key: str = "synthetic-key") -> None:
    load_settings(
        {
            "PSYEVO_ENV": environment,
            "PSYEVO_SUPPORT_MODE": "live",
            "PSYEVO_PROVIDER_API_KEY": key,
            "PSYEVO_DATABASE_URL": f"postgresql+psycopg://test:test@{host}/{database}",
        }
    )


def test_explicit_development_live_and_existing_test_live() -> None:
    config("development", "127.0.0.1", "psyevo_synthetic_dev")
    config("test", "127.0.0.1", "psyevo_synthetic_check_local")
    assert load_settings({}).support_mode == "disabled"


@pytest.mark.parametrize(
    ("environment", "host", "database", "key"),
    [
        ("development", "127.0.0.1", "psyevo_synthetic_dev", ""),
        ("development", "remote.example", "psyevo_synthetic_dev", "synthetic-key"),
        ("development", "127.0.0.1", "other", "synthetic-key"),
        ("test", "127.0.0.1", "psyevo_synthetic_dev", "synthetic-key"),
    ],
)
def test_live_rejects_unconfigured_or_wrong_database(
    environment: str, host: str, database: str, key: str
) -> None:
    with pytest.raises(ValidationError):
        config(environment, host, database, key)
