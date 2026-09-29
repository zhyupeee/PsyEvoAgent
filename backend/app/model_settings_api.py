"""Authenticated model settings; keys are write-only and probes are explicit."""

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import Field, SecretStr, ValidationError, field_validator
from sqlalchemy import select

from app.api import DB, APIError, Auth
from app.config import Settings
from app.contracts import Input
from app.models import Conversation, ProviderBinding, ProviderSettings, Run, TitleTask, now
from app.provider_config import official_settings
from app.provider_network import validate_base_url
from app.provider_settings import current, encrypt, for_owner

router = APIRouter(prefix="/api/v1/me/model-settings")


class Revision(Input):
    expected_version: int = Field(ge=0, strict=True)


class Change(Revision):
    mode: Literal["official", "custom"]
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    api_key: SecretStr | None = None
    deadline_seconds: float = Field(default=60, gt=0, le=120, allow_inf_nan=False)
    max_output_tokens: int = Field(default=1024, ge=1, le=4096, strict=True)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        return validate_base_url(value) if value is not None else None

    @field_validator("model")
    @classmethod
    def valid_model(cls, value: str | None) -> str | None:
        return Settings.provider_model_id(value) if value is not None else None

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            raw = value.get_secret_value()
            if not raw.strip() or len(raw) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in raw):
                raise ValueError("invalid_provider_key")
        return value


def check_version(row: ProviderSettings | None, expected: int) -> None:
    if (row.version if row is not None else 0) != expected:
        raise APIError(409, "version_conflict")


@router.get("")
def read(request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    row = current(db, auth.owner_id)
    base = request.app.state.settings
    try:
        official = official_settings(base)
        ready = official.support_mode == "live" and official.provider_ready
    except ValueError:
        official, ready = base, False
    return {
        "version": row.version if row else 0,
        "mode": row.mode if row else "official",
        "official": {"model": official.provider_model, "available": ready},
        "credential_storage_available": base.provider_encryption_key is not None,
        "custom": {
            "base_url": row.base_url or "" if row else "",
            "model": row.model or "" if row else "",
            "has_key": bool(row and row.encrypted_api_key),
            "deadline_seconds": row.deadline_seconds if row else 60,
            "max_output_tokens": row.max_output_tokens if row else 1024,
        },
    }


@router.patch("")
def change(body: Change, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    row = current(db, auth.owner_id)
    check_version(row, body.expected_version)
    if row is None:
        row = ProviderSettings(owner_id=auth.owner_id, version=0)
        db.add(row)
    if body.mode == "custom":
        if (
            not body.base_url
            or not body.model
            or (body.api_key is None and not row.encrypted_api_key)
        ):
            raise APIError(422, "provider_settings_incomplete")
        if request.app.state.settings.environment == "test" and body.max_output_tokens > 1024:
            raise APIError(422, "provider_output_limit")
        # Changing the destination requires re-entering the key. Never silently send
        # a previously saved service's credential to another host/path.
        if row.encrypted_api_key and row.base_url != body.base_url and body.api_key is None:
            raise APIError(422, "provider_key_required_for_address_change")
        row.base_url, row.model = body.base_url, body.model
        row.deadline_seconds, row.max_output_tokens = body.deadline_seconds, body.max_output_tokens
        if body.api_key is not None:
            try:
                row.encrypted_api_key = encrypt(
                    request.app.state.settings,
                    auth.owner_id,
                    "account-key",
                    {"key": body.api_key.get_secret_value()},
                )
            except ValueError:
                raise APIError(503, "provider_encryption_unavailable") from None
    row.mode, row.version, row.updated_at = body.mode, row.version + 1, now()
    db.flush()
    return read(request, db, auth)


@router.delete("")
def remove(body: Revision, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    from app.runs import execution, terminal

    row = current(db, auth.owner_id)
    check_version(row, body.expected_version)
    from app.provider_tests import cancel

    cancel(db, auth.owner_id, custom=True)
    if row is not None:
        row.mode, row.encrypted_api_key, row.base_url, row.model = "official", None, None, None
        row.version, row.updated_at = row.version + 1, now()
        for binding in db.scalars(
            select(ProviderBinding).where(
                ProviderBinding.owner_id == auth.owner_id, ProviderBinding.custom.is_(True)
            )
        ):
            binding.encrypted_config = None
            run = db.get(Run, binding.run_id)
            if run is not None and run.status in {"queued", "running"}:
                terminal(db, run, execution(db, run), "cancelled", "provider_configuration_revoked")
            for task in db.scalars(select(TitleTask).where(TitleTask.run_id == binding.run_id)):
                conversation = db.get(Conversation, task.session_id)
                if conversation and conversation.title_generation_status in {"queued", "running"}:
                    conversation.title_generation_status = "cancelled"
    db.flush()
    return read(request, db, auth)


@router.post("/test")
def test(body: Revision, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    from app.models import ProviderTest
    from app.provider_tests import execute, expire, reserve, result

    if request.app.state.settings.support_mode != "live":
        raise APIError(503, "provider_not_configured")
    key = request.headers.get("idempotency-key", "")
    if not 1 <= len(key) <= 128 or not key.isascii():
        raise APIError(422, "idempotency_key_required")
    previous = db.scalar(
        select(ProviderTest).where(
            ProviderTest.owner_id == auth.owner_id, ProviderTest.request_key == key
        )
    )
    if previous is not None:
        if previous.settings_version != body.expected_version:
            raise APIError(409, "idempotency_conflict")
        expire(previous)
        return result(previous)
    check_version(current(db, auth.owner_id), body.expected_version)
    try:
        selected = for_owner(db, request.app.state.settings, auth.owner_id)
    except (ValueError, ValidationError):
        raise APIError(503, "provider_configuration_unavailable") from None
    row = reserve(db, auth, key, body.expected_version, selected)
    owner, test_id = auth.owner_id, row.id
    db.commit()  # Durable reservation before I/O; do not hold the owner lock during transport.
    return asyncio.run(execute(request.app.state.engine, owner, test_id, selected))


@router.get("/test/{request_key}")
def test_receipt(request_key: str, db: DB, auth: Auth) -> dict[str, Any]:
    from app.models import ProviderTest
    from app.provider_tests import expire, result

    row = db.scalar(
        select(ProviderTest).where(
            ProviderTest.owner_id == auth.owner_id, ProviderTest.request_key == request_key
        )
    )
    if row is None:
        raise APIError(404, "not_found")
    expire(row)
    return {**result(row), "status": row.status, "receipt": row.receipt}
