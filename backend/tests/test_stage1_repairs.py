"""Real isolated database regressions for the stage-1 audit findings."""

import asyncio
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any
from uuid import uuid4

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.history import context_available, context_history
from app.models import ContextGrant, Message, ProviderTest, Run, RunExecution, now
from app.provider import open_provider
from app.support import Budget
from tests import test_runs
from tests.test_model_settings_api import PATH, configure, save
from tests.test_provider import response
from tests.test_runs import create, engine, start
from tests.test_support import request

pytestmark = pytest.mark.postgres
client = test_runs.client


def test_active_run_precedes_existing_empty_draft_and_rejects_new_draft(client: TestClient) -> None:
    sid, rid, body = create(client)
    draft_body = {"context_type": "conversation", "session_id": sid, "expected_session_version": 1}
    assert (
        client.post(
            "/api/v1/run-drafts", json=draft_body, headers={"Idempotency-Key": uuid4().hex}
        ).status_code
        == 201
    )
    start(client, rid, body)
    current = client.get(f"/api/v1/sessions/{sid}/current-run").json()
    assert current["run_id"] == rid and current["status"] == "queued"
    assert (
        client.post(
            "/api/v1/run-drafts", json=draft_body, headers={"Idempotency-Key": uuid4().hex}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/runs/{rid}/cancel", json={"expected_version": current["version"]}
        ).json()["status"]
        == "cancelled"
    )
    assert client.get(f"/api/v1/sessions/{sid}/current-run").json()["run_id"] == rid


@pytest.mark.parametrize("action", ["delete", "logout", "complete"])
def test_probe_reservation_replay_receipt_and_cancellation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    configure(client)
    save(client)
    started, stopped = threading.Event(), threading.Event()
    release: Future[None] = Future()
    calls = 0

    async def handle(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        started.set()
        try:
            await asyncio.wrap_future(release)
            return httpx.Response(
                200, content=response(), headers={"content-type": "text/event-stream"}
            )
        finally:
            stopped.set()

    @asynccontextmanager
    async def provider(settings: Any) -> Any:
        async with open_provider(settings, transport=httpx.MockTransport(handle)) as adapter:
            yield adapter

    monkeypatch.setattr("app.provider_probe.open_provider", provider)
    key = uuid4().hex
    headers = {"Idempotency-Key": key}
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(
            client.post, PATH + "/test", json={"expected_version": 1}, headers=headers
        )
        try:
            assert started.wait(10)
            with Session(engine(client)) as db:
                row = db.scalar(select(ProviderTest).where(ProviderTest.request_key == key))
                assert row and row.receipt["status"] == "reserved"
                assert row.receipt["reserved_tokens"] == 8192
            replay = client.post(PATH + "/test", json={"expected_version": 1}, headers=headers)
            assert replay.json() == {"passed": False, "reason": "provider_test_running"}
            denied = client.post(
                PATH + "/test",
                json={"expected_version": 1},
                headers={"Idempotency-Key": uuid4().hex},
            )
            assert denied.status_code == 409 and denied.json()["code"] == "provider_test_active"
            if action == "delete":
                assert (
                    client.request("DELETE", PATH, json={"expected_version": 1}).status_code == 200
                )
            elif action == "logout":
                assert client.post("/api/v1/auth/logout").status_code == 204
            else:
                release.set_result(None)
            result = pending.result(timeout=10)
            assert result.status_code == 200
            assert result.json()["passed"] is (action == "complete")
            assert stopped.wait(2) and calls == 1
            with Session(engine(client)) as db:
                row = db.scalar(select(ProviderTest).where(ProviderTest.request_key == key))
                assert row and row.status == ("completed" if action == "complete" else "cancelled")
                assert row.receipt["role"] == "configuration_test"
                assert (
                    row.receipt["actual_tokens"] is not None
                    if action == "complete"
                    else (row.receipt["actual_tokens"] is None)
                )
            if action != "logout":
                assert (
                    client.post(
                        PATH + "/test", json={"expected_version": 1}, headers=headers
                    ).json()
                    == result.json()
                )
                assert calls == 1
            if action == "complete":
                assert (
                    client.post(
                        PATH + "/test",
                        json={"expected_version": 1},
                        headers={"Idempotency-Key": uuid4().hex},
                    ).status_code
                    == 429
                )
        finally:
            if not release.done():
                release.set_result(None)


def test_expired_probe_is_not_reissued(client: TestClient) -> None:
    configure(client)
    sid, rid, body = create(client)
    start(client, rid, body)
    with Session(engine(client)) as db, db.begin():
        run = db.get(Run, rid)
        ex = db.scalar(select(RunExecution).where(RunExecution.run_id == rid))
        assert run and ex
        db.add(
            ProviderTest(
                owner_id=run.owner_id,
                identity_id=ex.identity_id,
                request_key="lost-request",
                settings_version=0,
                custom=False,
                deadline_at=now() - timedelta(seconds=1),
                receipt={"reserved_tokens": 8192, "actual_tokens": None},
            )
        )
    result = client.post(
        PATH + "/test", json={"expected_version": 0}, headers={"Idempotency-Key": "lost-request"}
    )
    assert result.json() == {"passed": False, "reason": "deadline"}
    assert client.get(PATH + "/test/lost-request").json()["status"] == "interrupted"


def test_bulk_history_bounds_queries_and_rechecks_revocation(client: TestClient) -> None:
    sid, rid, body = create(client)
    start(client, rid, body)
    with Session(engine(client)) as db, db.begin():
        run = db.get(Run, rid)
        ex = db.scalar(select(RunExecution).where(RunExecution.run_id == rid))
        assert run and ex
        run.status = "completed"
        db.add(Message(owner_id=run.owner_id, run_id=rid, role="assistant", content="合成回复"))
        for index in range(24):
            prior = Run(
                owner_id=run.owner_id,
                session_id=sid,
                session_version=1,
                status="completed",
                source_message_version=1,
            )
            db.add(prior)
            db.flush()
            grant = ContextGrant(
                owner_id=run.owner_id,
                run_id=prior.id,
                source_id=sid,
                source_version=1,
                purpose="current_run",
            )
            db.add(grant)
            db.flush()
            db.add(
                RunExecution(
                    owner_id=run.owner_id,
                    run_id=prior.id,
                    identity_id=ex.identity_id,
                    request_hash="a" * 64,
                    versions=ex.versions,
                    budget=ex.budget,
                    grant_ids=[grant.id],
                    preference="listen",
                    deadline_at=now(),
                )
            )
            db.add_all(
                [
                    Message(
                        owner_id=run.owner_id, run_id=prior.id, role=role, content=f"合成{index}"
                    )
                    for role in ("user", "assistant")
                ]
            )
        current = Run(owner_id=run.owner_id, session_id=sid, session_version=1)
        db.add(current)
        db.flush()
        current_id, grant_id = current.id, grant.id
    queries: list[str] = []

    def count(*args: Any) -> None:
        queries.append(str(args[2]))

    event.listen(engine(client), "before_cursor_execute", count)
    try:
        timeline = client.get(f"/api/v1/sessions/{sid}/timeline")
        assert timeline.status_code == 200 and len(timeline.json()["items"]) == 20
        assert len(queries) <= 15
        with Session(engine(client)) as db:
            active_run = db.get(Run, current_id)
            assert active_run
            queries.clear()
            turns = context_history(db, active_run, request(), Budget())
            assert len(turns) == 25 and len(queries) <= 5
            queries.clear()
            assert context_available(db, active_run, turns) and len(queries) <= 5
        with Session(engine(client)) as db, db.begin():
            revoked = db.get(ContextGrant, grant_id)
            assert revoked
            revoked.revoked_at = now()
        with Session(engine(client)) as db:
            active_run = db.get(Run, current_id)
            assert active_run and not context_available(db, active_run, turns)
    finally:
        event.remove(engine(client), "before_cursor_execute", count)
