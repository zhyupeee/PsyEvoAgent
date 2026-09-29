"""Owner-scoped credentials and immutable private snapshots for accepted runs."""

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import ProviderBinding, ProviderSettings


def cipher(settings: Settings) -> Fernet:
    if settings.provider_encryption_key is None:
        raise ValueError("provider_encryption_unavailable")
    try:
        return Fernet(settings.provider_encryption_key.get_secret_value().encode())
    except ValueError:
        raise ValueError("provider_encryption_unavailable") from None


def encrypt(settings: Settings, owner: str, context: str, value: dict[str, Any]) -> str:
    payload = json.dumps({"owner": owner, "context": context, "value": value})
    return cipher(settings).encrypt(payload.encode()).decode()


def decrypt(settings: Settings, owner: str, context: str, token: str) -> dict[str, Any]:
    try:
        payload = json.loads(cipher(settings).decrypt(token.encode()))
        if payload["owner"] != owner or payload["context"] != context:
            raise ValueError("provider_key_unreadable")
        result: dict[str, Any] = payload["value"]
        return result
    except (InvalidToken, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        raise ValueError("provider_key_unreadable") from None


def current(db: Session, owner: str) -> ProviderSettings | None:
    return db.scalar(select(ProviderSettings).where(ProviderSettings.owner_id == owner))


def for_owner(db: Session, settings: Settings, owner: str) -> Settings:
    from app.provider_config import official_settings

    row = current(db, owner)
    if row is None or row.mode == "official":
        return official_settings(settings)
    if not row.base_url or not row.model or not row.encrypted_api_key:
        raise ValueError("provider_settings_incomplete")
    key = decrypt(settings, owner, "account-key", row.encrypted_api_key)["key"]
    return Settings.model_validate(
        {
            **settings.model_dump(),
            "provider_base_url": row.base_url,
            "provider_model": row.model,
            "provider_api_key": SecretStr(key),
            "provider_deadline_seconds": row.deadline_seconds,
            "provider_max_output_tokens": row.max_output_tokens,
            "provider_custom_endpoint": True,
        }
    )


def freeze(db: Session, settings: Settings, owner: str, run_id: str) -> None:
    # Historical explicit test/live callers without encrypted storage remain supported.
    # Ordinary development startup initializes independent encryption first.
    if settings.provider_encryption_key is None:
        if settings.provider_custom_endpoint:
            raise ValueError("provider_encryption_unavailable")
        return
    assert settings.provider_api_key is not None
    value = {
        "provider_base_url": settings.provider_base_url,
        "provider_model": settings.provider_model,
        "provider_api_key": settings.provider_api_key.get_secret_value(),
        "provider_deadline_seconds": settings.provider_deadline_seconds,
        "provider_max_output_tokens": settings.provider_max_output_tokens,
        "provider_custom_endpoint": settings.provider_custom_endpoint,
    }
    db.add(
        ProviderBinding(
            run_id=run_id,
            owner_id=owner,
            custom=settings.provider_custom_endpoint,
            encrypted_config=encrypt(settings, owner, run_id, value),
        )
    )


def available(db: Session, owner: str, run_id: str) -> bool:
    binding = db.get(ProviderBinding, run_id)
    return binding is None or (binding.owner_id == owner and binding.encrypted_config is not None)


def for_run(db: Session, settings: Settings, owner: str, run_id: str) -> Settings:
    binding = db.get(ProviderBinding, run_id)
    if binding is None:
        return settings  # Preserve frozen model checks for legacy runs.
    if binding.owner_id != owner or binding.encrypted_config is None:
        raise ValueError("provider_configuration_revoked")
    value = decrypt(settings, owner, run_id, binding.encrypted_config)
    return Settings.model_validate({**settings.model_dump(), **value})
