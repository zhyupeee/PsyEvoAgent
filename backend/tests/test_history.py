"""STEP07 acceptance on disposable PostgreSQL; no development data or live model."""

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import deletion
from app.models import (
    ContextGrant,
    Conversation,
    Feedback,
    Message,
    ModelCall,
    Run,
    RunBranch,
    RunEvent,
    now,
)
from app.run_worker import claim, execute, execute_one
from tests import test_runs
from tests.test_runs import create, engine, start
from tests.test_support import ScriptedModel, message

client = test_runs.client
other_client = test_runs.client
pytestmark = pytest.mark.postgres


def post(client: TestClient, path: str, body: dict[str, Any], key: str | None = None) -> Response:
    return client.post("/api/v1" + path, json=body, headers={"Idempotency-Key": key or uuid4().hex})


def current(client: TestClient, sid: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/sessions/{sid}/current-run")
    assert response.status_code == 200, response.text
    return dict(response.json())


def remove(client: TestClient, sid: str, key: str | None = None) -> Response:
    return client.request(
        "DELETE",
        f"/api/v1/sessions/{sid}",
        json={"expected_version": 1, "confirmed": True},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


@pytest.mark.parametrize("invalid", ["revoked", "deleted", "source_version"])
def test_draft_branch_rechecks_inherited_sources(client: TestClient, invalid: str) -> None:
    sid, rid, body = create(client, grant=True)
    start(client, rid, body)
    assert execute_one(engine(client))
    old = current(client, sid)
    response = post(
        client,
        f"/sessions/{sid}/messages/{old['input_id']}/revisions",
        {"content": "synthetic private revision", "expected_version": old["input_version"]},
    )
    assert response.status_code == 201, response.text
    branch = response.json()
    assert current(client, sid)["input_text"] == "synthetic private revision"
    with Session(engine(client)) as db, db.begin():
        grant = db.scalar(select(ContextGrant).where(ContextGrant.run_id == branch["run_id"]))
        assert grant is not None
        if invalid == "revoked":
            grant.revoked_at = now()
        elif invalid == "deleted":
            grant.deleted_at = now()
        else:
            grant.source_version += 1
    for path in [f"/sessions/{sid}/current-run", f"/runs/{branch['run_id']}"]:
        result = client.get("/api/v1" + path)
        assert result.status_code == 404, result.text
        assert "synthetic private revision" not in result.text
    history = client.get(f"/api/v1/sessions/{sid}/history")
    assert history.status_code == 200
    assert branch["run_id"] not in [turn["run_id"] for turn in history.json()["items"]]
    assert "synthetic private revision" not in history.text


def test_feedback_idempotency_optional_reason_and_scope(client: TestClient) -> None:
    sid, rid, body = create(client)
    start(client, rid, body)
    feedback = {
        "run_id": rid,
        "helpfulness": "unhelpful",
        "category": "misunderstood",
        "comment": "",
    }
    assert post(client, "/feedback", feedback).status_code == 409
    assert execute_one(engine(client))
    key = uuid4().hex
    result = post(client, "/feedback", feedback, key)
    assert result.status_code == 201, result.text
    assert post(client, "/feedback", feedback, key).json() == result.json()
    assert post(client, "/feedback", {**feedback, "comment": "different"}, key).status_code == 409
    assert post(client, "/feedback", {**feedback, "transcript": "forbidden"}).status_code == 422
    with Session(engine(client)) as db:
        rows = list(db.scalars(select(Feedback).where(Feedback.run_id == rid)))
        assert len(rows) == 1 and rows[0].comment == "" and rows[0].source_refs == []
        assert body["input"]["message"] not in str(rows[0].__dict__)
    assert remove(client, sid).json()["status"] == "completed"
    assert post(client, "/feedback", feedback, key).status_code == 404


def test_delete_real_content_events_grants_feedback_and_replay(client: TestClient) -> None:
    sid, rid, body = create(client, grant=True)
    start(client, rid, body)
    assert execute_one(engine(client))
    assert post(client, "/feedback", {"run_id": rid, "helpfulness": "helpful"}).status_code == 201
    assert (
        client.request(
            "DELETE", f"/api/v1/sessions/{sid}", json={"expected_version": 1}
        ).status_code
        == 422
    )
    key = uuid4().hex
    result = remove(client, sid, key)
    assert result.status_code == 202, result.text
    receipt = result.json()
    assert receipt["status"] == "completed" and receipt["remaining_steps"] == []
    assert remove(client, sid, key).json() == receipt
    assert client.get("/api/v1/deletion-jobs/" + receipt["deletion_id"]).json() == receipt
    for path in [
        f"/sessions/{sid}",
        f"/sessions/{sid}/history",
        f"/sessions/{sid}/current-run",
        f"/runs/{rid}",
        f"/runs/{rid}/events",
        "/context-grants/" + body["grant_ids"][0],
    ]:
        response = client.get("/api/v1" + path)
        assert response.status_code == 404, (path, response.text)
        assert body["input"]["message"] not in response.text
    with Session(engine(client)) as db:
        assert all(
            m.content == "" and m.deleted_at
            for m in db.scalars(select(Message).where(Message.run_id == rid))
        )
        assert (
            db.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.run_id == rid)) == 0
        )
        assert (
            db.scalar(select(func.count()).select_from(Feedback).where(Feedback.run_id == rid)) == 0
        )
        source = db.get(Conversation, sid)
        assert source is not None and source.title == "已删除的对话"
        grant = db.get(ContextGrant, body["grant_ids"][0])
        assert grant is not None and grant.deleted_at and grant.revoked_at


def test_delete_failure_is_durable_retryable_and_never_reopens(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid, rid, body = create(client)
    start(client, rid, body)
    assert execute_one(engine(client))
    original = deletion.purge_step

    def fail(db: Session, job: Any, step: str) -> None:
        if step == "events":
            raise RuntimeError("synthetic cleanup failure, must never be exposed")
        original(db, job, step)

    monkeypatch.setattr(deletion, "purge_step", fail)
    result = remove(client, sid)
    assert result.status_code == 202, result.text
    receipt = result.json()
    assert receipt["status"] == "failed_retryable"
    assert receipt["completed_steps"] == ["online_blocked", "messages"]
    assert "events" in receipt["remaining_steps"] and "synthetic cleanup" not in result.text
    assert client.get(f"/api/v1/runs/{rid}/events").status_code == 404
    with Session(engine(client)) as db:
        source = db.get(Conversation, sid)
        assert source is not None and source.deleted_at
        assert (
            db.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.run_id == rid)) or 0
        ) > 0
    monkeypatch.setattr(deletion, "purge_step", original)
    retried = post(
        client,
        "/deletion-jobs/" + receipt["deletion_id"] + "/retry",
        {"expected_version": receipt["version"]},
    )
    assert retried.json()["status"] == "completed", retried.text
    assert client.get(f"/api/v1/sessions/{sid}").status_code == 404


def test_revision_regeneration_branch_context_and_idempotency(client: TestClient) -> None:
    sid, rid, body = create(client)
    start(client, rid, body)
    old = current(client, sid)
    path = f"/sessions/{sid}/messages/{old['input_id']}/revisions"
    revised = {"content": "更正后的合成输入", "expected_version": old["input_version"]}
    assert post(client, path, revised).status_code == 409
    client.post(f"/api/v1/runs/{rid}/cancel", json={"expected_version": 2})
    key = uuid4().hex
    response = post(client, path, revised, key)
    assert response.status_code == 201, response.text
    branch = response.json()
    assert post(client, path, revised, key).json()["run_id"] == branch["run_id"]
    assert branch["input_version"] == 2 and branch["parent_run_id"] == rid
    start(
        client,
        branch["run_id"],
        {
            "expected_version": 1,
            "expected_session_version": 1,
            "input": {"source_message_id": branch["input_id"]},
            "client_message_id": uuid4().hex,
        },
    )
    chosen = claim(engine(client))
    assert chosen and chosen[0] == branch["run_id"]
    fake = ScriptedModel(cache=False, responses=[], outcomes=[message()])
    asyncio.run(execute(engine(client), chosen[0], chosen[1], fake))
    assert revised["content"] in str(fake.captures)
    assert body["input"]["message"] not in str(fake.captures)
    rows = client.get(f"/api/v1/sessions/{sid}/history").json()["items"]
    assert len(rows) == 2 and rows[0]["is_current"] and not rows[1]["is_current"]
    assert post(client, path, revised).status_code == 409
    regen_key = uuid4().hex
    regen_body = {
        "kind": "regenerate",
        "expected_session_version": 1,
        "client_message_id": uuid4().hex,
        "input": {"source_message_id": branch["input_id"]},
    }
    result = post(client, f"/sessions/{sid}/runs", regen_body, regen_key)
    assert result.status_code == 202, result.text
    assert (
        post(client, f"/sessions/{sid}/runs", regen_body, regen_key).json()["run_id"]
        == result.json()["run_id"]
    )
    assert execute_one(engine(client))
    assert current(client, sid)["input_version"] == 3
    assert current(client, sid)["input_text"] == revised["content"]
    with Session(engine(client)) as db:
        parent = db.get(Run, rid)
        assert parent is not None
        assert (
            db.scalar(
                select(func.count())
                .select_from(RunBranch)
                .where(RunBranch.owner_id == parent.owner_id)
            )
            == 2
        )


def test_history_search_archive_versions_and_source_revoke(client: TestClient) -> None:
    sid, rid, body = create(client, grant=True)
    start(client, rid, body)
    assert execute_one(engine(client))
    for version, patch in [
        (1, {"title": "合成检索_标题"}),
        (2, {"status": "archived"}),
        (3, {"status": "active"}),
    ]:
        result = client.patch(
            f"/api/v1/sessions/{sid}", json={"expected_version": version, **patch}
        )
        assert result.status_code == 200, result.text
        assert current(client, sid)["input_text"] == body["input"]["message"]
        listed = client.get(
            "/api/v1/sessions", params={"q": "检索_", "status": result.json()["status"]}
        ).json()
        assert [item["id"] for item in listed["items"]] == [sid]
    assert (
        client.patch(
            f"/api/v1/sessions/{sid}", json={"expected_version": 1, "title": "stale"}
        ).status_code
        == 409
    )
    client.request(
        "DELETE", "/api/v1/context-grants/" + body["grant_ids"][0], json={"expected_version": 1}
    )
    assert client.get(f"/api/v1/sessions/{sid}/history").json()["items"] == []


def test_delete_inflight_fences_late_output_and_preserves_usage(client: TestClient) -> None:
    sid, rid, body = create(client)
    start(client, rid, body)
    chosen = claim(engine(client))
    assert chosen is not None
    fake = ScriptedModel(cache=False, responses=[], outcomes=[message()], delay=0.3)

    async def race() -> None:
        task = asyncio.create_task(execute(engine(client), rid, chosen[1], fake))
        for _ in range(100):
            if fake.calls:
                break
            await asyncio.sleep(0.01)
        assert fake.calls == 1
        response = await asyncio.to_thread(remove, client, sid)
        assert response.json()["status"] == "completed", response.text
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(race())
    with Session(engine(client)) as db:
        run = db.get(Run, rid)
        assert run is not None and run.status == "cancelled" and run.deleted_at
        calls = list(db.scalars(select(ModelCall).where(ModelCall.run_id == rid)))
        assert len(calls) == 1 and calls[0].receipt["actual_tokens"] is None
        reserved = calls[0].receipt["reserved_tokens"]
        assert isinstance(reserved, int) and reserved > 0
        assert (
            db.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.run_id == rid)) == 0
        )
        assert all(
            row.content == "" for row in db.scalars(select(Message).where(Message.run_id == rid))
        )


def test_history_feedback_revision_delete_are_owner_scoped(
    client: TestClient, other_client: TestClient
) -> None:
    sid, rid, body = create(client)
    start(client, rid, body)
    assert execute_one(engine(client))
    old = current(client, sid)
    # A separate isolated account, leaving all business ownership unchanged.
    other = other_client
    assert other.get(f"/api/v1/sessions/{sid}/history").status_code == 404
    assert other.get("/api/v1/sessions").json()["items"] == []
    assert post(other, "/feedback", {"run_id": rid, "helpfulness": "helpful"}).status_code == 404
    assert (
        post(
            other,
            f"/sessions/{sid}/messages/{old['input_id']}/revisions",
            {"content": "wrong owner", "expected_version": 1},
        ).status_code
        == 404
    )
    assert remove(other, sid).status_code == 404
    receipt = remove(client, sid).json()
    assert other.get("/api/v1/deletion-jobs/" + receipt["deletion_id"]).status_code == 404
    assert (
        post(
            other,
            "/deletion-jobs/" + receipt["deletion_id"] + "/retry",
            {"expected_version": receipt["version"]},
        ).status_code
        == 404
    )


def test_delete_source_cleans_derived_regenerated_runs(client: TestClient) -> None:
    source_id, _, _ = create(client)
    sid, rid, body = create(client)
    grant = post(
        client,
        "/context-grants",
        {
            "run_id": rid,
            "source_type": "conversation",
            "source_id": source_id,
            "source_version": 1,
            "purpose": "current_run",
        },
    )
    assert grant.status_code == 201
    body["grant_ids"] = [grant.json()["id"]]
    start(client, rid, body)
    assert execute_one(engine(client))
    prior = current(client, sid)
    regen = post(
        client,
        f"/sessions/{sid}/runs",
        {
            "kind": "regenerate",
            "expected_session_version": 1,
            "client_message_id": uuid4().hex,
            "input": {"source_message_id": prior["input_id"]},
        },
    )
    assert regen.status_code == 202, regen.text
    assert execute_one(engine(client))
    assert remove(client, source_id).json()["status"] == "completed"
    assert client.get(f"/api/v1/sessions/{sid}/history").json()["items"] == []
    for run_id in [rid, regen.json()["run_id"]]:
        assert client.get(f"/api/v1/runs/{run_id}/events").status_code == 404
        with Session(engine(client)) as db:
            assert all(
                row.content == ""
                for row in db.scalars(select(Message).where(Message.run_id == run_id))
            )


def test_cursor_pagination_and_no_persistent_checkpointer(client: TestClient) -> None:
    from app.run_worker import fake_model
    from app.support import ModelProfile, SupportRuntime

    runtime = SupportRuntime(fake_model(), profile=ModelProfile(), authorize=lambda _: True)
    assert runtime.graph.checkpointer is None
    ids = [create(client)[0] for _ in range(3)]
    response = client.get("/api/v1/sessions", params={"limit": 2}).json()
    assert len(response["items"]) == 2 and response["next_cursor"]
    following = client.get(
        "/api/v1/sessions", params={"limit": 2, "cursor": response["next_cursor"]}
    ).json()
    assert len(following["items"]) == 1 and following["next_cursor"] is None
    assert {row["id"] for row in response["items"] + following["items"]} == set(ids)
    assert client.get("/api/v1/sessions", params={"cursor": uuid4().hex}).status_code == 422
