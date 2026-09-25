"""STEP05 real isolated PostgreSQL / authenticated API acceptance."""

import asyncio
import json
import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import (
    ContextGrant,
    Conversation,
    IdentitySession,
    Interaction,
    Message,
    ModelCall,
    Preferences,
    Run,
    RunEvent,
    RunExecution,
    User,
    now,
)
from app.run_worker import claim, execute, execute_one, fake_model
from app.runs import emit, execution, lock_owner, terminal
from app.security import digest
from tests.test_support import message as fake_message
from tests.test_support import model as delayed_model

pytestmark = pytest.mark.postgres
ORIGIN = "https://synthetic.local"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(
        Settings(
            environment="test",
            support_mode="fake",
            database_url=SecretStr(os.environ["PSYEVO_TEST_DATABASE_URL"]),
            browser_origin=ORIGIN,
        )
    )
    with TestClient(app, base_url=ORIGIN) as client:
        token = uuid4().hex
        with Session(app.state.engine) as db, db.begin():
            user = User(email=uuid4().hex + "@example.com", password_hash="synthetic-unused")
            db.add(user)
            db.flush()
            db.add(Preferences(owner_id=user.id))
            auth = IdentitySession(
                owner_id=user.id,
                token_hash=digest(token),
                csrf_token="test-csrf",
                expires_at=now() + timedelta(hours=1),
            )
            db.add(auth)
        client.cookies.set("psyevo_session", token)
        client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": "test-csrf"})
        try:
            yield client
        finally:
            client.post("/api/v1/auth/logout")


def create(client: TestClient, *, grant: bool = False) -> tuple[str, str, dict[str, Any]]:
    sid = client.post("/api/v1/sessions", json={}, headers={"Idempotency-Key": uuid4().hex}).json()[
        "id"
    ]
    draft = client.post(
        "/api/v1/run-drafts",
        json={"context_type": "conversation", "session_id": sid, "expected_session_version": 1},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert draft.status_code == 201, draft.text
    rid = draft.json()["run_id"]
    body: dict[str, Any] = {
        "input": {"message": "合成输入，只想倾听"},
        "expected_version": 1,
        "expected_session_version": 1,
        "client_message_id": uuid4().hex,
    }
    if grant:
        response = client.post(
            "/api/v1/context-grants",
            json={
                "run_id": rid,
                "source_type": "conversation",
                "source_id": sid,
                "source_version": 1,
                "purpose": "current_run",
            },
            headers={"Idempotency-Key": uuid4().hex},
        )
        assert response.status_code == 201, response.text
        body["grant_ids"] = [response.json()["id"]]
    return sid, rid, body


def start(
    client: TestClient, rid: str, body: dict[str, Any], key: str | None = None
) -> dict[str, Any]:
    result = client.post(
        f"/api/v1/runs/{rid}/start", json=body, headers={"Idempotency-Key": key or uuid4().hex}
    )
    assert result.status_code == 202, result.text
    return dict(result.json())


def engine(client: TestClient) -> Engine:
    assert isinstance(client.app, FastAPI)
    result = client.app.state.engine
    assert isinstance(result, Engine)
    return result


def events(client: TestClient, rid: str, cursor: str = "0") -> list[dict[str, Any]]:
    result = client.get(f"/api/v1/runs/{rid}/events?after_event_id={cursor}")
    assert result.status_code == 200, result.text
    assert result.headers["x-accel-buffering"] == "no"
    return [json.loads(line[6:]) for line in result.text.splitlines() if line.startswith("data: ")]


def test_draft_start_replay_and_persisted_output(client: TestClient) -> None:
    _, rid, body = create(client, grant=True)
    with Session(engine(client)) as db:
        assert (
            db.scalar(select(func.count()).select_from(ModelCall).where(ModelCall.run_id == rid))
            == 0
        )
    assert events(client, rid) == []
    key = uuid4().hex
    first = start(client, rid, body, key)
    assert first["status"] == "queued" and first["version"] == 2
    assert start(client, rid, body, key)["run_id"] == rid
    assert start(client, rid, body)["run_id"] == rid
    changed = {**body, "input": {"message": "different"}}
    assert (
        client.post(
            f"/api/v1/runs/{rid}/start", json=changed, headers={"Idempotency-Key": key}
        ).status_code
        == 409
    )
    assert execute_one(engine(client))
    final = client.get(f"/api/v1/runs/{rid}").json()
    assert final["status"] == "completed" and final["output"]["version"] == 1
    stream = events(client, rid)
    assert [e["type"] for e in stream] == ["run.started", "message.delta", "run.completed"]
    assert [e["event_id"] for e in stream] == ["1", "2", "3"]
    assert [e["run_version"] for e in stream] == [3, 3, 4]
    assert events(client, rid, "1") == stream[1:]
    assert events(client, rid, "3") == []
    assert start(client, rid, body, key)["status"] == "completed"
    assert (
        client.post(f"/api/v1/runs/{rid}/cancel", json={"expected_version": 1}).json()["status"]
        == "completed"
    )
    with Session(engine(client)) as db:
        assert len(db.scalars(select(ModelCall).where(ModelCall.run_id == rid)).all()) == 1
        assert len(db.scalars(select(Interaction).where(Interaction.run_id == rid)).all()) == 1
        assert len(db.scalars(select(Message).where(Message.run_id == rid)).all()) == 2


def test_disabled_provider_replays_persisted_start(client: TestClient) -> None:
    _, rid, body = create(client)
    key = uuid4().hex
    first = start(client, rid, body, key)
    assert isinstance(client.app, FastAPI)
    settings = client.app.state.settings
    client.app.state.settings = settings.model_copy(update={"support_mode": "disabled"})

    replay = client.post(f"/api/v1/runs/{rid}/start", json=body, headers={"Idempotency-Key": key})
    assert replay.status_code == 202, replay.text
    assert replay.json() == first
    with Session(engine(client)) as db:
        assert len(db.scalars(select(Message).where(Message.run_id == rid)).all()) == 1
        assert len(db.scalars(select(Interaction).where(Interaction.run_id == rid)).all()) == 1


@pytest.mark.parametrize("phase", ["draft", "queued", "running"])
def test_cancel_terminal_and_no_late_output(client: TestClient, phase: str) -> None:
    _, rid, body = create(client)
    if phase != "draft":
        start(client, rid, body)
    if phase == "running":
        assert claim(engine(client)) is not None
    version = client.get(f"/api/v1/runs/{rid}").json()["version"]
    if version > 1:
        assert (
            client.post(f"/api/v1/runs/{rid}/cancel", json={"expected_version": 1}).status_code
            == 409
        )
    result = client.post(f"/api/v1/runs/{rid}/cancel", json={"expected_version": version})
    assert result.json()["status"] == "cancelled"
    assert (
        client.post(f"/api/v1/runs/{rid}/cancel", json={"expected_version": 1}).json()["status"]
        == "cancelled"
    )
    assert client.post(
        f"/api/v1/runs/{rid}/start", json=body, headers={"Idempotency-Key": uuid4().hex}
    ).status_code in {202, 409}
    assert all(e["type"] != "message.delta" for e in events(client, rid))


def test_parallel_start_and_cas_race(client: TestClient) -> None:
    _, rid, body = create(client)
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(start, client, rid, body) for _ in range(2)]
        assert all(f.result()["run_id"] == rid for f in futures)
    selected = claim(engine(client))
    assert selected is not None and selected[0] == rid
    barrier = threading.Barrier(2)

    def finish(status: str) -> bool:
        barrier.wait()
        with Session(engine(client)) as db, db.begin():
            lock_owner(db, selected[1])
            row = db.get(Run, rid)
            assert row is not None
            return terminal(db, row, execution(db, row), status, "synthetic-race")

    with ThreadPoolExecutor(2) as pool:
        results = [pool.submit(finish, status) for status in ("completed", "cancelled")]
        assert sorted(f.result() for f in results) == [False, True]
    assert (
        len([e for e in events(client, rid) if e["type"] in {"run.completed", "run.cancelled"}])
        == 1
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "source_deleted",
        "source_version",
        "grant_revoked",
        "owner",
        "message_deleted",
        "message_version",
    ],
)
def test_replay_and_snapshot_reauthorize(client: TestClient, mutation: str) -> None:
    sid, rid, body = create(client, grant=True)
    start(client, rid, body)
    assert execute_one(engine(client))
    with Session(engine(client)) as db, db.begin():
        source = db.get(Conversation, sid)
        assert source is not None
        if mutation == "source_deleted":
            source.deleted_at = now()
        elif mutation == "source_version":
            source.version += 1
        elif mutation == "grant_revoked":
            grant = db.get(ContextGrant, body["grant_ids"][0])
            assert grant is not None
            grant.revoked_at = now()
        elif mutation.startswith("message_"):
            message = db.scalar(
                select(Message).where(Message.run_id == rid, Message.role == "user")
            )
            assert message is not None
            if mutation == "message_deleted":
                message.deleted_at = now()
            else:
                message.version += 1
        else:
            # Authenticated alternate owner, never mutate business ownership.
            other = User(email=uuid4().hex + "@example.com", password_hash="synthetic")
            db.add(other)
            db.flush()
            token = uuid4().hex
            db.add(
                IdentitySession(
                    owner_id=other.id,
                    token_hash=digest(token),
                    csrf_token="test-csrf",
                    expires_at=now() + timedelta(hours=1),
                )
            )
            client.cookies.set("psyevo_session", token)
    for suffix in ("", "/events?after_event_id=1"):
        response = client.get(f"/api/v1/runs/{rid}" + suffix)
        assert response.status_code == 404 and "合成测试回应" not in response.text


def test_cursor_handshake_expiry_and_snapshot(client: TestClient) -> None:
    _, rid, body = create(client)
    start(client, rid, body)
    assert execute_one(engine(client))
    for cursor in ("-1", "01", "abc", "999"):
        assert client.get(f"/api/v1/runs/{rid}/events?after_event_id={cursor}").status_code == 422
    assert (
        client.get(
            f"/api/v1/runs/{rid}/events?after_event_id=1", headers={"Last-Event-ID": "2"}
        ).status_code
        == 422
    )
    assert client.get(f"/api/v1/runs/{rid}/events", headers={"Last-Event-ID": "3"}).text == ""
    with Session(engine(client)) as db, db.begin():
        run = db.get(Run, rid)
        assert run is not None
        ex = execution(db, run)
        assert ex is not None
        # Exercise the actual bounded persistence writer, not a fabricated HTTP 410.
        for _ in range(130):
            emit(db, run, ex, "run.completed", {"synthetic_retention_probe": True})
    assert client.get(f"/api/v1/runs/{rid}/events?after_event_id=1").status_code == 410
    assert client.get(f"/api/v1/runs/{rid}").json()["output"]["text"]
    with Session(engine(client)) as db:
        assert (
            db.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.run_id == rid))
            == 128
        )


def test_deadline_recovery_logout_and_disabled_provider(client: TestClient) -> None:
    _, rid, body = create(client)
    start(client, rid, body)
    selected = claim(engine(client))
    assert selected and selected[0] == rid
    with Session(engine(client)) as db, db.begin():
        ex = db.scalar(select(RunExecution).where(RunExecution.run_id == rid))
        assert ex is not None
        ex.deadline_at = now() - timedelta(seconds=1)
    claim(engine(client))
    assert client.get(f"/api/v1/runs/{rid}").json()["status"] == "interrupted"
    assert events(client, rid)[-1]["type"] == "run.failed"
    _, rid2, body2 = create(client)
    start(client, rid2, body2)
    assert client.post("/api/v1/auth/logout").status_code == 204
    with Session(engine(client)) as db:
        run = db.get(Run, rid2)
        assert run is not None and run.status == "cancelled"
    assert client.get(f"/api/v1/runs/{rid}/events").status_code == 401


def test_deadline_expires_after_claim_before_execute(client: TestClient) -> None:
    _, rid, body = create(client)
    start(client, rid, body)
    selected = claim(engine(client))
    assert selected and selected[0] == rid
    with Session(engine(client)) as db, db.begin():
        ex = db.scalar(select(RunExecution).where(RunExecution.run_id == rid))
        assert ex is not None
        ex.deadline_at = now() - timedelta(seconds=1)

    asyncio.run(execute(engine(client), rid, selected[1]))

    final = client.get(f"/api/v1/runs/{rid}").json()
    assert final["status"] == "interrupted"
    assert final["stop_reason"] == "interrupted"
    assert [event["type"] for event in events(client, rid)] == ["run.started", "run.failed"]


def test_deadline_expires_during_model_call(client: TestClient) -> None:
    _, rid, body = create(client)
    start(client, rid, body)
    selected = claim(engine(client))
    assert selected and selected[0] == rid
    adapter = delayed_model(fake_message(), delay=5)

    async def expire_inflight() -> None:
        task = asyncio.create_task(execute(engine(client), rid, selected[1], adapter))
        for _ in range(100):
            if adapter.calls:
                break
            await asyncio.sleep(0.01)
        assert adapter.calls == 1
        with Session(engine(client)) as db, db.begin():
            lock_owner(db, selected[1])
            ex = db.scalar(select(RunExecution).where(RunExecution.run_id == rid))
            assert ex is not None
            ex.deadline_at = now() - timedelta(seconds=1)
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(expire_inflight())
    final = client.get(f"/api/v1/runs/{rid}").json()
    assert final["status"] == "interrupted"
    assert final["stop_reason"] == "interrupted"
    assert [event["type"] for event in events(client, rid)] == ["run.started", "run.failed"]
    with Session(engine(client)) as db:
        calls = db.scalars(select(ModelCall).where(ModelCall.run_id == rid)).all()
        assert len(calls) == 1 and calls[0].receipt["actual_cost"] is None


@pytest.mark.parametrize("convenience", [False, True])
def test_start_rejects_nul_message(client: TestClient, convenience: bool) -> None:
    sid, rid, body = create(client)
    body["input"]["message"] = "hello\x00world"
    path = f"/api/v1/sessions/{sid}/runs" if convenience else f"/api/v1/runs/{rid}/start"
    response = client.post(path, json=body, headers={"Idempotency-Key": uuid4().hex})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert response.json()["retryable"] is False
    with Session(engine(client)) as db:
        run = db.get(Run, rid)
        assert run is not None and run.status == "draft"
        assert db.scalar(select(Message.id).where(Message.run_id == rid)) is None


@pytest.mark.parametrize("outcome", ["unsafe", "unknown_usage", "cancel"])
def test_worker_output_gate_and_unknown_cost(client: TestClient, outcome: str) -> None:
    _, rid, body = create(client)
    start(client, rid, body)
    selected = claim(engine(client))
    assert selected and selected[0] == rid
    model = fake_model()
    if outcome == "unsafe":
        model.responses = [
            AIMessage(
                content=json.dumps({"text": "先倾听。你只需要我。"}),
                usage_metadata={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            )
        ]
    elif outcome == "unknown_usage":
        model.responses = [AIMessage(content='{"text":"synthetic"}')]
    else:
        client.post(f"/api/v1/runs/{rid}/cancel", json={"expected_version": 3})
    asyncio.run(execute(engine(client), rid, selected[1], model))
    assert not any(e["type"] == "message.delta" for e in events(client, rid))
    with Session(engine(client)) as db:
        calls = db.scalars(select(ModelCall).where(ModelCall.run_id == rid)).all()
        if outcome == "unknown_usage":
            assert calls[0].receipt["actual_cost"] is None
            tokens = calls[0].receipt["reserved_tokens"]
            assert isinstance(tokens, int) and tokens > 0
        elif outcome == "cancel":
            assert calls == []
        assert "合成输入" not in json.dumps([c.receipt for c in calls], ensure_ascii=False)


def test_interaction_dedupe_union_idle_and_clock_drift(client: TestClient) -> None:
    _, rid, body = create(client)
    start(client, rid, body)
    timestamp = now().isoformat()
    batch = {
        "events": [
            {
                "event_id": uuid4().hex,
                "run_id": rid,
                "event_type": "active_segment",
                "initiation": initiation,
                "occurred_at": timestamp,
                "segment": {
                    "tab_id": uuid4().hex,
                    "sequence": 1,
                    "start_ms": 100,
                    "end_ms": 2100,
                    "visible": visible,
                    "focused": True,
                },
            }
            for initiation, visible in [
                ("user", True),
                ("requested_followup", True),
                ("system_push", False),
            ]
        ]
    }
    first = client.post("/api/v1/interaction-events", json=batch)
    assert first.status_code == 200, first.text
    assert first.json()["accepted"] == 3 and first.json()["reported_union_ms"] == 2000
    assert first.json()["active_ms"] is None
    assert client.post("/api/v1/interaction-events", json=batch).json()["duplicate"] == 3
    drift = {
        "events": [
            {
                **batch["events"][0],
                "event_id": uuid4().hex,
                "occurred_at": (now() - timedelta(days=1)).isoformat(),
            }
        ]
    }
    assert client.post("/api/v1/interaction-events", json=drift).json()["rejected"] == 1
    with Session(engine(client)) as db:
        rows = db.scalars(select(Interaction).where(Interaction.run_id == rid)).all()
        assert len(rows) == 4 and sum(r.event_type == "message_sent" for r in rows) == 1


def test_send_convenience_client_id_and_csrf(client: TestClient) -> None:
    sid, _, body = create(client)
    body["kind"] = "message"
    path = f"/api/v1/sessions/{sid}/runs"
    denied = client.post(
        path, json=body, headers={"Idempotency-Key": uuid4().hex, "X-CSRF-Token": "bad"}
    )
    assert denied.status_code == 403
    first = client.post(path, json=body, headers={"Idempotency-Key": uuid4().hex})
    assert first.status_code == 202, first.text
    repeat = client.post(path, json=body, headers={"Idempotency-Key": uuid4().hex})
    assert repeat.status_code == 202 and repeat.json()["run_id"] == first.json()["run_id"]


@pytest.mark.parametrize("length", [123, 124, 128])
def test_message_sent_recorded_at_client_id_limit(client: TestClient, length: int) -> None:
    _, rid, body = create(client)
    body["client_message_id"] = "m" * length
    key = uuid4().hex
    start(client, rid, body, key)
    start(client, rid, body, key)
    with Session(engine(client)) as db:
        rows = db.scalars(select(Interaction).where(Interaction.run_id == rid)).all()
        assert len(rows) == 1
        assert rows[0].event_type == "message_sent"
        assert len(rows[0].event_key) <= 128


@pytest.mark.parametrize("stop", ["cancel", "logout", "delete_source"])
def test_inflight_stop_persists_unknown_charge(client: TestClient, stop: str) -> None:
    sid, rid, body = create(client)
    start(client, rid, body)
    selected = claim(engine(client))
    assert selected and selected[0] == rid
    adapter = delayed_model(fake_message(), delay=5)

    async def check() -> None:
        task = asyncio.create_task(execute(engine(client), rid, selected[1], adapter))
        for _ in range(100):
            if adapter.calls:
                break
            await asyncio.sleep(0.01)
        assert adapter.calls == 1
        with Session(engine(client)) as db:
            reservation = db.scalar(select(ModelCall).where(ModelCall.run_id == rid))
            assert reservation is not None and reservation.receipt["status"] == "reserved"
            assert reservation.receipt["actual_cost"] is None
        if stop == "cancel":
            response = await asyncio.to_thread(
                client.post, f"/api/v1/runs/{rid}/cancel", json={"expected_version": 3}
            )
            assert response.status_code == 200
        elif stop == "logout":
            assert (await asyncio.to_thread(client.post, "/api/v1/auth/logout")).status_code == 204
        else:
            with Session(engine(client)) as db, db.begin():
                lock_owner(db, selected[1])
                source = db.get(Conversation, sid)
                assert source is not None
                source.deleted_at = now()
        await asyncio.wait_for(task, timeout=1)

    asyncio.run(check())
    with Session(engine(client)) as db:
        row = db.get(Run, rid)
        assert row is not None and row.status == "cancelled"
        calls = db.scalars(select(ModelCall).where(ModelCall.run_id == rid)).all()
        assert len(calls) == 1 and calls[0].receipt["status"] == "cancelled"
        assert calls[0].receipt["actual_cost"] is None
        assert (
            db.scalar(select(Message.id).where(Message.run_id == rid, Message.role == "assistant"))
            is None
        )


def test_start_failure_is_atomic_and_no_disabled_live_execution(client: TestClient) -> None:
    _, rid, body = create(client)
    bad = {**body, "expected_session_version": 999}
    assert (
        client.post(
            f"/api/v1/runs/{rid}/start", json=bad, headers={"Idempotency-Key": uuid4().hex}
        ).status_code
        == 409
    )
    with Session(engine(client)) as db:
        row = db.get(Run, rid)
        assert row is not None and row.status == "draft" and row.version == 1
        assert execution(db, row) is None
        assert db.scalar(select(Message.id).where(Message.run_id == rid)) is None
    assert isinstance(client.app, FastAPI)
    settings = client.app.state.settings
    client.app.state.settings = settings.model_copy(update={"support_mode": "disabled"})
    response = client.post(
        f"/api/v1/runs/{rid}/start", json=body, headers={"Idempotency-Key": uuid4().hex}
    )
    assert response.status_code == 503 and response.json()["code"] == "provider_not_configured"


def test_optional_event_storage_failure_does_not_block_support(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, rid, body = create(client)
    original = Session.add

    def fail_optional(db: Session, instance: object, _warn: bool = True) -> None:
        if isinstance(instance, Interaction):
            raise SQLAlchemyError("synthetic optional storage failure")
        original(db, instance, _warn=_warn)

    monkeypatch.setattr(Session, "add", fail_optional)
    assert start(client, rid, body)["status"] == "queued"
    assert execute_one(engine(client))
    assert client.get(f"/api/v1/runs/{rid}").json()["status"] == "completed"
    with Session(engine(client)) as db:
        assert db.scalar(select(Interaction.id).where(Interaction.run_id == rid)) is None
