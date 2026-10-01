"""No database or live model is needed to check that the probe fails closed."""

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.jobs import JobSource, require_probe


def test_probe_requires_synthetic_configuration() -> None:
    for settings in (Settings(), Settings(environment="test")):
        with pytest.raises(ValueError, match="Job probe"):
            require_probe(settings)
    with pytest.raises(ValidationError):
        Settings(
            environment="test",
            support_mode="fake",
            database_url=SecretStr("postgresql+psycopg://fake@127.0.0.1/psyevo_synthetic_dev"),
        )


def test_job_refs_reject_body_and_unimplemented_purposes() -> None:
    ref = {"source_type": "note", "source_id": "0" * 36, "source_version": 1}
    for fields in (
        {"content": "private"},
        {"purpose": "current_run"},
        {"source_type": "memory"},
        {"source_version": True},
        {"source_id": "../../private"},
    ):
        with pytest.raises(ValidationError):
            JobSource.model_validate({**ref, **fields})
