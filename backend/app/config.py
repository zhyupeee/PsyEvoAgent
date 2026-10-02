"""Read only explicitly supported process variables; never auto-load .env files."""

import os
from collections.abc import Mapping
from ipaddress import IPv6Address
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
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
    support_mode: Literal["disabled", "fake", "live"] = "disabled"
    memory_mode: Literal["disabled", "fake", "live"] = "disabled"
    # STEP08 internal PoC only; this does not enable the API or Worker.
    live_probe_enabled: bool = False
    provider_base_url: str = "https://ai.hybgzs.com/v1"
    provider_model: str = "grok-4.7"
    provider_api_key: SecretStr | None = None
    provider_encryption_key: SecretStr | None = None
    provider_config_file: str | None = None
    provider_custom_endpoint: bool = False
    provider_deadline_seconds: float = Field(default=60, gt=0, le=120, allow_inf_nan=False)
    provider_max_output_tokens: int = Field(default=1024, ge=1, le=4096, strict=True)

    @property
    def provider_ready(self) -> bool:
        return bool(self.provider_api_key and self.provider_api_key.get_secret_value().strip())

    @field_validator("provider_base_url")
    @classmethod
    def provider_https(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or any(c.isspace() for c in value)
        ):
            raise ValueError("Provider requires an HTTPS base URL without credentials or query")
        return value.rstrip("/")

    @field_validator("provider_model")
    @classmethod
    def provider_model_id(cls, value: str) -> str:
        if not value.strip() or len(value) > 200 or any(c.isspace() for c in value):
            raise ValueError("An exact model ID is required")
        return value

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
        if self.memory_mode != "disabled" and (
            self.database_url is None or self.memory_mode != self.support_mode
        ):
            raise ValueError("Memory requires the matching explicitly configured Support mode")
        if self.environment == "test" and self.provider_max_output_tokens > 1024:
            raise ValueError("Synthetic acceptance retains its 1024 output token limit")
        if self.support_mode == "live" and (
            self.database_url is None
            or (not self.provider_ready and self.provider_encryption_key is None)
        ):
            raise ValueError("Live support requires explicit credentials and a database")
        if self.support_mode == "live" and self.environment == "development":
            assert self.database_url is not None
            url = make_url(self.database_url.get_secret_value())
            if url.host not in {"127.0.0.1", "localhost"} or url.database != "psyevo_synthetic_dev":
                raise ValueError("Development live support requires the local development database")
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
            "memory_mode": source.get("PSYEVO_MEMORY_MODE", "disabled"),
            "live_probe_enabled": source.get("PSYEVO_LIVE_PROBE_ENABLED", "false"),
            "provider_base_url": source.get("PSYEVO_PROVIDER_BASE_URL", "https://ai.hybgzs.com/v1"),
            "provider_model": source.get("PSYEVO_PROVIDER_MODEL", "grok-4.7"),
            "provider_api_key": source.get("PSYEVO_PROVIDER_API_KEY"),
            "provider_encryption_key": source.get("PSYEVO_PROVIDER_ENCRYPTION_KEY"),
            "provider_config_file": source.get("PSYEVO_PROVIDER_CONFIG_FILE"),
            "provider_deadline_seconds": source.get("PSYEVO_PROVIDER_DEADLINE_SECONDS", "60"),
            "provider_max_output_tokens": int(
                source.get("PSYEVO_PROVIDER_MAX_OUTPUT_TOKENS", "1024")
            ),
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
