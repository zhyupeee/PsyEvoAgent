"""Read only explicitly supported process variables; never auto-load .env files."""

import os
from collections.abc import Mapping
from ipaddress import IPv6Address
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator, model_validator
from sqlalchemy.engine import make_url


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    environment: Literal["development", "test"] = "development"
    database_url: SecretStr | None = None
    browser_origin: str = "http://127.0.0.1:3000"
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_from: str | None = None
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_tls_mode: Literal["starttls", "ssl"] | None = None
    email_code_key: SecretStr | None = None
    support_mode: Literal["disabled", "fake"] = "disabled"

    @property
    def email_ready(self) -> bool:
        return bool(
            self.smtp_host
            and self.smtp_port
            and 0 < self.smtp_port < 65536
            and self.smtp_from
            and self.smtp_username
            and self.smtp_password
            and self.smtp_password.get_secret_value()
            and self.smtp_tls_mode
            and self.email_code_key
            and len(self.email_code_key.get_secret_value()) >= 32
        )

    @field_validator("database_url")
    @classmethod
    def explicit_postgres_database(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            url = make_url(value.get_secret_value())
            if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
                raise ValueError("An explicit PostgreSQL host and database are required")
        return value

    @field_validator("browser_origin")
    @classmethod
    def single_origin(cls, value: str) -> str:
        url = urlsplit(value)
        hostname = url.hostname
        if (
            not hostname
            or any(character.isspace() for character in value)
            or url.username is not None
            or url.password is not None
            or url.path
            or url.query
            or url.fragment
            or url.scheme not in {"https", "http"}
            or (url.scheme == "http" and hostname not in {"127.0.0.1", "localhost", "::1"})
        ):
            raise ValueError("Configure one HTTPS Origin without a path; HTTP is loopback-only")
        port = url.port
        host = (
            f"[{IPv6Address(hostname).compressed}]"
            if ":" in hostname
            else hostname.encode("idna").decode("ascii")
        )
        default_port = 443 if url.scheme == "https" else 80
        suffix = f":{port}" if port is not None and port != default_port else ""
        return f"{url.scheme}://{host}{suffix}"

    @model_validator(mode="after")
    def isolated_test_database(self) -> "Settings":
        if self.support_mode == "fake" and (
            self.environment != "test" or self.database_url is None
        ):
            raise ValueError("Fake support requires an isolated synthetic test database")
        if self.environment == "test" and self.database_url is not None:
            url = make_url(self.database_url.get_secret_value())
            if url.host not in {"127.0.0.1", "localhost"} or not (url.database or "").startswith(
                ("psyevo_synthetic_check", "psyevo_synthetic_migration_")
            ):
                raise ValueError("Tests require an isolated local synthetic check database")
        return self


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if environ is None else environ
    return Settings.model_validate(
        {
            "environment": source.get("PSYEVO_ENV", "development"),
            "support_mode": source.get("PSYEVO_SUPPORT_MODE", "disabled"),
            "database_url": source.get("PSYEVO_DATABASE_URL"),
            "browser_origin": source.get("PSYEVO_BROWSER_ORIGIN", "http://127.0.0.1:3000"),
            **{
                field: source.get("PSYEVO_" + field.upper())
                for field in (
                    "smtp_host",
                    "smtp_port",
                    "smtp_from",
                    "smtp_username",
                    "smtp_password",
                    "smtp_tls_mode",
                    "email_code_key",
                )
            },
        }
    )
