import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.contracts import Register


def test_explicit_remote_configuration_and_test_isolation() -> None:
    url = SecretStr("postgresql+psycopg://example:placeholder@db.example/experiment")
    assert Settings(database_url=url, browser_origin="https://app.example").database_url == url
    for origin in (
        "http://app.example",
        "https://app.example/",
        "https://a.example https://b.example",
        "https://u:p@app.example",
        "https://app.example?x=1",
    ):
        with pytest.raises(ValidationError):
            Settings(browser_origin=origin)
    for database in (url, SecretStr("postgresql+psycopg://a:b@127.0.0.1/psyevo_synthetic_dev")):
        with pytest.raises(ValidationError):
            Settings(environment="test", database_url=database)
    assert (
        Register(email="plain@example.com", code="123456", password="12345678").password
        == "12345678"
    )
