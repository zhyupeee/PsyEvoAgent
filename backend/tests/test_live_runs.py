"""Real PostgreSQL + controlled SDK transport; never a remote provider."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2 as httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Message, ModelCall, Run, RunEvent
from app.provider import InternalStreamProvider, LiveProfile, open_provider
from app.run_worker import claim, execute, execute_one
from tests import test_runs
from tests.test_history import remove
from tests.test_provider import PausedStream, response
from tests.test_runs import create, engine, start

client = test_runs.client
pytestmark = pytest.mark.postgres


def live_settings(client: TestClient) -> Settings:
    assert isinstance(client.app, FastAPI)
    config = client.app.state.settings.model_copy(
        update={
            "support_mode": "live",
            "provider_api_key": SecretStr("synthetic-key"),
        }
    )
    config = Settings.model_validate(config.model_dump())
    client.app.state.settings = config
    return config


@pytest.mark.parametrize("cancel", [False, True])
def test_live_buffer_persistence_and_cancel(client: TestClient, cancel: bool) -> None:
    config = live_settings(client)
    sid, rid, body = create(client)
    started = start(client, rid, body)
    assert started["budget"]["max_cost"] is None
    assert started["version_binding"]["provider_ref"] == config.provider_base_url
    with Session(engine(client)) as db:
        run = db.get(Run, rid)
        assert run is not None
        owner = run.owner_id
    assert claim(engine(client)) == (rid, owner)

    async def exercise() -> None:
        stream = PausedStream()

        async def handle(req: httpx.Request) -> httpx.Response:
            if cancel:
                return httpx.Response(
                    200, stream=stream, headers={"content-type": "text/event-stream"}
                )
            return httpx.Response(
                200, content=response(), headers={"content-type": "text/event-stream"}
            )

        async with open_provider(config, transport=httpx.MockTransport(handle)) as adapter:
            task = asyncio.create_task(
                execute(
                    engine(client),
                    rid,
                    owner,
                    adapter,
                    LiveProfile(model_ref=config.provider_model, base_url=config.provider_base_url),
                )
            )
            if cancel:
                await asyncio.wait_for(stream.started.wait(), 2)
                with Session(engine(client)) as db:
                    assert not [
                        e
                        for e in db.scalars(select(RunEvent).where(RunEvent.run_id == rid))
                        if e.envelope["type"] == "message.delta"
                    ]
                snapshot = client.get(f"/api/v1/runs/{rid}").json()
                stopped = client.post(
                    f"/api/v1/runs/{rid}/cancel", json={"expected_version": snapshot["version"]}
                )
                assert stopped.status_code == 200
            await task
            if cancel:
                assert stream.closed

    asyncio.run(exercise())
    snapshot = client.get(f"/api/v1/runs/{rid}").json()
    assert snapshot["status"] == ("cancelled" if cancel else "completed")
    assert (snapshot["output"] is None) == cancel
    with Session(engine(client)) as db:
        calls = db.scalars(select(ModelCall).where(ModelCall.run_id == rid)).all()
        assert len(calls) == 1 and calls[0].receipt["actual_cost"] is None
        assert calls[0].receipt["status"] == ("cancelled" if cancel else "settled")
    deleted = remove(client, sid)
    assert deleted.status_code == 202
    assert deleted.json()["external_provider_status"] == "unknown"
    # A later API restart with disabled provider must not relabel earlier live calls N/A.
    assert isinstance(client.app, FastAPI)
    client.app.state.settings = config.model_copy(update={"support_mode": "disabled"})
    result = client.get("/api/v1/deletion-jobs/" + deleted.json()["deletion_id"])
    assert result.json()["external_provider_status"] == "unknown"


@pytest.mark.parametrize("fault", ["write", "commit_ack"])
def test_live_completion_transaction_failure_does_not_repeat_call(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    config = live_settings(client)
    _, rid, body = create(client)
    start(client, rid, body)
    calls = 0
    injected = False

    async def handle(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200, content=response(), headers={"content-type": "text/event-stream"}
        )

    @asynccontextmanager
    async def provider(settings: Settings) -> AsyncIterator[InternalStreamProvider]:
        async with open_provider(settings, transport=httpx.MockTransport(handle)) as adapter:
            yield adapter

    def before_flush(db: Session, context: object, instances: object) -> None:
        nonlocal injected
        if any(
            isinstance(row, Message) and row.run_id == rid and row.role == "assistant"
            for row in db.new
        ):
            db.info["live_completion"] = True
            if fault == "write" and not injected:
                injected = True
                raise SQLAlchemyError("synthetic completion write failure")

    def after_commit(db: Session) -> None:
        nonlocal injected
        if fault == "commit_ack" and db.info.get("live_completion") and not injected:
            injected = True
            raise SQLAlchemyError("synthetic commit acknowledgement lost")

    monkeypatch.setattr("app.run_worker.open_provider", provider)
    event.listen(Session, "before_flush", before_flush)
    event.listen(Session, "after_commit", after_commit)
    try:
        assert execute_one(engine(client), config)
    finally:
        event.remove(Session, "before_flush", before_flush)
        event.remove(Session, "after_commit", after_commit)
    assert injected and calls == 1
    snapshot = client.get(f"/api/v1/runs/{rid}").json()
    assert snapshot["status"] == ("failed" if fault == "write" else "completed")
    assert (snapshot["output"] is None) == (fault == "write")
    with Session(engine(client)) as db:
        rows = db.scalars(select(RunEvent).where(RunEvent.run_id == rid)).all()
        assert sum(row.envelope["type"] == "message.delta" for row in rows) == (fault != "write")
        assert len(db.scalars(select(ModelCall).where(ModelCall.run_id == rid)).all()) == 1
    assert not execute_one(engine(client), config)
    assert calls == 1  # Recovery reads committed facts; it never reissues the provider request.


@pytest.mark.parametrize(
    "field,value",
    [("provider_model", "different-model"), ("provider_base_url", "https://different.example/v1")],
)
def test_live_configuration_drift_rejects_before_network(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    config = live_settings(client)
    _, rid, body = create(client)
    start(client, rid, body)
    calls = 0

    async def handle(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise AssertionError("Configuration drift must never reach the provider")

    @asynccontextmanager
    async def provider(settings: Settings) -> AsyncIterator[InternalStreamProvider]:
        async with open_provider(settings, transport=httpx.MockTransport(handle)) as adapter:
            yield adapter

    monkeypatch.setattr("app.run_worker.open_provider", provider)
    assert execute_one(engine(client), config.model_copy(update={field: value}))
    assert calls == 0
    snapshot = client.get(f"/api/v1/runs/{rid}").json()
    assert snapshot["status"] == "failed" and snapshot["output"] is None
    assert snapshot["budget_used"]["calls"] == 0
