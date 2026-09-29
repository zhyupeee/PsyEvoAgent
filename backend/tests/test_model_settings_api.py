"""Isolated database and real SDK with synthetic transports; no remote requests."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any
from uuid import uuid4

import httpx2 as httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    Conversation,
    IdentitySession,
    Message,
    Preferences,
    ProviderBinding,
    ProviderSettings,
    Run,
    RunExecution,
    User,
    now,
)
from app.provider import InternalStreamProvider, open_provider
from app.provider_settings import for_run
from app.run_worker import execute_one
from app.security import digest
from app.titles import execute_one as execute_title
from tests import test_runs
from tests.test_provider import response
from tests.test_runs import create, engine, start

pytestmark = pytest.mark.postgres
client = test_runs.client
PATH = "/api/v1/me/model-settings"


def configure(client: TestClient) -> Settings:
    assert isinstance(client.app, FastAPI)
    settings = Settings.model_validate(
        {
            **client.app.state.settings.model_dump(),
            "support_mode": "live",
            "provider_api_key": SecretStr("synthetic-official"),
            "provider_encryption_key": SecretStr(Fernet.generate_key().decode()),
        }
    )
    client.app.state.settings = settings
    return settings


def save(client: TestClient, **changes: Any) -> dict[str, Any]:
    body = {
        "expected_version": 0,
        "mode": "custom",
        "base_url": "https://example.com/v1",
        "model": "custom-one",
        "api_key": "synthetic-personal-secret",
        "max_output_tokens": 1024,
        **changes,
    }
    result = client.patch(PATH, json=body)
    assert result.status_code == 200, result.text
    assert "synthetic-personal-secret" not in result.text
    return dict(result.json())


def test_saved_key_encryption_revisions_and_mode_switch(client: TestClient) -> None:
    configure(client)
    assert client.get(PATH).json()["version"] == 0
    saved = save(client)
    assert saved["custom"]["has_key"] and saved["version"] == 1
    with Session(engine(client)) as db:
        row = db.scalar(
            select(ProviderSettings)
            .where(ProviderSettings.model == "custom-one")
            .order_by(ProviderSettings.created_at.desc())
        )
        assert row is not None and row.encrypted_api_key
        assert "synthetic-personal-secret" not in row.encrypted_api_key
    assert client.patch(PATH, json={"mode": "official", "expected_version": 0}).status_code == 409
    result = client.patch(PATH, json={"mode": "official", "expected_version": 1})
    assert result.json()["custom"]["has_key"]  # Switching modes is not deletion.
    assert result.json()["mode"] == "official"
    assert (
        client.patch(
            PATH,
            json={
                "mode": "custom",
                "expected_version": 2,
                "base_url": "https://other.example/v1",
                "model": "two",
            },
        ).status_code
        == 422
    )
    assert (
        client.patch(
            PATH,
            json={
                "mode": "custom",
                "expected_version": 2,
                "base_url": "https://127.0.0.1/v1",
                "model": "two",
                "api_key": "never-echo-this",
            },
        ).status_code
        == 422
    )


def test_binding_survives_save_and_titles_use_same_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = configure(client)
    save(client)
    sid, rid, body = create(client)
    assert start(client, rid, body)["version_binding"]["model_ref"] == "custom-one"
    save(client, expected_version=1, model="custom-two", api_key="synthetic-new-key")
    calls: list[str] = []

    @asynccontextmanager
    async def controlled(bound: Settings) -> AsyncIterator[InternalStreamProvider]:
        async def handle(req: httpx.Request) -> httpx.Response:
            assert bound.provider_model == "custom-one"
            assert req.headers["authorization"] == "Bearer synthetic-personal-secret"
            calls.append(bound.provider_model)
            text = '{"text":"我先听你说。"}' if len(calls) == 1 else '{"title":"压力与休息"}'
            return httpx.Response(
                200, content=response(text), headers={"content-type": "text/event-stream"}
            )

        async with open_provider(bound, transport=httpx.MockTransport(handle)) as provider:
            yield provider

    monkeypatch.setattr("app.run_worker.open_provider", controlled)
    monkeypatch.setattr("app.titles.open_provider", controlled)
    assert execute_one(engine(client), settings)
    # Other tests can leave valid title jobs in the shared isolated database.
    # This test targets credential binding; queue ordering is tested separately.
    with Session(engine(client)) as db, db.begin():
        source = db.get(Conversation, sid)
        run = db.get(Run, rid)
        assert source is not None and run is not None
        source.title_generation_status = "running"
        owner = run.owner_id
    monkeypatch.setattr("app.titles.claim", lambda _: (sid, owner))
    assert execute_title(engine(client), settings)
    with Session(engine(client)) as db:
        run = db.get(Run, rid)
        source = db.get(Conversation, sid)
        assert run is not None and run.status == "completed"
        assert source is not None and source.title == "压力与休息"
        assert source.title_generation_status == "succeeded"
    assert calls == ["custom-one", "custom-one"]


def test_delete_revokes_snapshots_and_queued_runs(client: TestClient) -> None:
    settings = configure(client)
    save(client)
    _, rid, body = create(client)
    start(client, rid, body)
    deleted = client.request("DELETE", PATH, json={"expected_version": 1})
    assert deleted.status_code == 200 and not deleted.json()["custom"]["has_key"]
    with Session(engine(client)) as db:
        run, binding = db.get(Run, rid), db.get(ProviderBinding, rid)
        assert run is not None and binding is not None
        assert run.status == "cancelled" and binding.encrypted_config is None
        with pytest.raises(ValueError, match="revoked"):
            for_run(db, settings, run.owner_id, rid)


def test_official_snapshot_is_independent_from_next_process_config(client: TestClient) -> None:
    settings = configure(client)
    _, rid, body = create(client)
    start(client, rid, body)
    changed = settings.model_copy(
        update={"provider_model": "new-official", "provider_api_key": SecretStr("new-key")}
    )
    with Session(engine(client)) as db:
        run = db.get(Run, rid)
        assert run is not None
        bound = for_run(db, changed, run.owner_id, rid)
        assert bound.provider_model == settings.provider_model
        assert bound.provider_api_key == settings.provider_api_key
        with pytest.raises(ValueError):
            for_run(db, settings, str(uuid4()), rid)


def test_test_endpoint_requires_live_and_is_explicit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.post(PATH + "/test", json={"expected_version": 0}).status_code == 503
    configure(client)
    calls: list[str] = []

    async def probe(settings: Settings, **kwargs: Any) -> dict[str, object]:
        calls.append(settings.provider_model)
        return {"status": "passed", "stop_reason": None}

    monkeypatch.setattr("app.provider_probe.probe", probe)
    save(client)
    assert calls == []
    result = client.post(
        PATH + "/test", json={"expected_version": 1}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert result.json() == {"passed": True, "reason": None}
    assert calls == ["custom-one"]
    assert (
        client.patch(
            PATH,
            headers={"X-CSRF-Token": "wrong"},
            json={"mode": "official", "expected_version": 1},
        ).status_code
        == 403
    )


def test_personal_mode_works_without_official_key(client: TestClient) -> None:
    settings = configure(client)
    assert isinstance(client.app, FastAPI)
    client.app.state.settings = Settings.model_validate(
        {**settings.model_dump(), "provider_api_key": None}
    )
    assert not client.get(PATH).json()["official"]["available"]
    save(client)
    _, rid, body = create(client)
    started = start(client, rid, body)
    assert started["version_binding"]["model_ref"] == "custom-one"


def test_probe_releases_owner_lock_before_provider_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure(client)
    save(client)
    _, rid, _ = create(client)
    with Session(engine(client)) as db:
        run = db.get(Run, rid)
        assert run is not None
        owner = run.owner_id

    async def probe(settings: Settings, **kwargs: Any) -> dict[str, object]:
        with Session(engine(client)) as db, db.begin():
            row = db.scalar(select(ProviderSettings).where(ProviderSettings.owner_id == owner))
            assert row is not None
            # NOWAIT fails immediately if the request still holds the owner lock.
            assert db.scalar(
                select(User).where(User.id == row.owner_id).with_for_update(nowait=True)
            )
            row.model = "changed-during-probe"
        assert settings.provider_model == "custom-one"
        return {"status": "passed", "stop_reason": None}

    monkeypatch.setattr("app.provider_probe.probe", probe)
    result = client.post(
        PATH + "/test", json={"expected_version": 1}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert result.status_code == 200
    assert result.json() == {"passed": True, "reason": None}
    assert client.get(PATH).json()["custom"]["model"] == "changed-during-probe"


@pytest.mark.parametrize("explicit_official", [False, True])
def test_missing_official_key_rejects_start_without_execution(
    client: TestClient, explicit_official: bool
) -> None:
    settings = configure(client)
    assert isinstance(client.app, FastAPI)
    client.app.state.settings = Settings.model_validate(
        {**settings.model_dump(), "provider_api_key": None}
    )
    if explicit_official:
        assert (
            client.patch(PATH, json={"mode": "official", "expected_version": 0}).status_code == 200
        )
    _, rid, body = create(client)
    result = client.post(
        f"/api/v1/runs/{rid}/start", json=body, headers={"Idempotency-Key": uuid4().hex}
    )
    assert result.status_code == 503
    assert "provider_configuration_unavailable" in result.text
    with Session(engine(client)) as db:
        run = db.get(Run, rid)
        assert run is not None and run.status == "draft" and run.version == 1
        assert db.scalar(select(RunExecution).where(RunExecution.run_id == rid)) is None
        assert db.get(ProviderBinding, rid) is None
        assert db.scalar(select(Message).where(Message.run_id == rid)) is None


def test_second_account_cannot_read_or_delete_first_key(client: TestClient) -> None:
    configure(client)
    save(client)
    token = uuid4().hex
    with Session(engine(client)) as db, db.begin():
        user = User(email=uuid4().hex + "@example.com", password_hash="synthetic")
        db.add(user)
        db.flush()
        db.add(Preferences(owner_id=user.id))
        db.add(
            IdentitySession(
                owner_id=user.id,
                token_hash=digest(token),
                csrf_token="test-csrf",
                expires_at=now() + timedelta(hours=1),
            )
        )
    old_token = client.cookies.get("psyevo_session")
    client.cookies.clear()
    client.cookies.set("psyevo_session", token)
    other = client.get(PATH).json()
    assert other["version"] == 0 and not other["custom"]["has_key"]
    assert client.request("DELETE", PATH, json={"expected_version": 1}).status_code == 409
    client.cookies.clear()
    assert old_token is not None
    client.cookies.set("psyevo_session", old_token)
    assert client.get(PATH).json()["custom"]["has_key"]
