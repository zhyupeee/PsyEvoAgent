"""S2-STEP04: actual LangMem, isolated PostgreSQL and synthetic fault injection."""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, BaseMessage
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import deletion, jobs, memory_worker
from app.memory import source_key, suppressed
from app.memory_models import Memory, MemoryCandidate, MemorySuppression
from app.models import BackgroundJob, ContextGrant, JobBudget, Note
from app.run_worker import execute_one
from tests import test_runs
from tests.test_history import current, remove
from tests.test_jobs import child_env
from tests.test_records import saved_note
from tests.test_records import write as record_write
from tests.test_runs import engine

client = test_runs.client
other = test_runs.client
pytestmark = pytest.mark.postgres


def write(
    client: TestClient, method: str, path: str, body: dict[str, Any], key: str | None = None
) -> Any:
    return record_write(client, method, path.removeprefix("/api/v1"), body, key)


def enable(client: TestClient) -> None:
    assert isinstance(client.app, FastAPI)
    client.app.state.settings = client.app.state.settings.model_copy(update={"memory_mode": "fake"})


def pending(client: TestClient) -> tuple[dict[str, Any], str]:
    enable(client)
    note = saved_note(client)
    with Session(engine(client)) as db:
        source = db.get(Note, note["id"])
        assert source
        job = db.scalar(
            select(BackgroundJob).where(
                BackgroundJob.owner_id == source.owner_id, BackgroundJob.kind == "memory_extraction"
            )
        )
        assert job is not None
        return note, job.id


def lease(client: TestClient, jid: str) -> jobs.Lease:
    # Tests leave no runnable jobs from earlier cases.
    with Session(engine(client)) as db, db.begin():
        for row in db.scalars(
            select(BackgroundJob).where(
                BackgroundJob.id != jid,
                BackgroundJob.kind == "memory_extraction",
                BackgroundJob.status.in_(jobs.ACTIVE),
            )
        ):
            jobs.finish(row, "cancelled", "test_cleanup", jobs.clock(db))
    result = jobs.claim(engine(client), str(uuid4()), kind="memory_extraction")
    assert result and result.job_id == jid
    return result


def run(client: TestClient, jid: str, **kwargs: Any) -> None:
    assert isinstance(client.app, FastAPI)
    asyncio.run(
        memory_worker.execute(
            engine(client), client.app.state.settings, lease(client, jid), **kwargs
        )
    )


def state(client: TestClient, jid: str) -> dict[str, Any]:
    return dict(client.get("/api/v1/jobs/" + jid).json())


def test_automatic_langmem_save_owner_dedupe_and_forget(
    client: TestClient, other: TestClient
) -> None:
    note, jid = pending(client)
    run(client, jid)
    assert state(client, jid)["status"] == "succeeded"
    items = client.get("/api/v1/memories").json()["items"]
    assert len(items) == 1 and items[0]["claim_type"] == "user_statement"
    row = items[0]
    assert row["event_time"] is None
    assert row["content"] in (note["body"] + note["title"])
    candidates = client.get("/api/v1/memory-candidates").json()["items"]
    assert len(candidates) == 1 and candidates[0]["memory_id"] == row["id"]
    assert other.get("/api/v1/memories/" + row["id"]).status_code == 404
    assert other.get("/api/v1/memory-candidates/" + candidates[0]["id"]).status_code == 404
    response = write(
        client,
        "post",
        "/api/v1/memory-candidates",
        {
            "source_refs": [
                {"source_type": "note", "source_id": note["id"], "source_version": note["version"]}
            ]
        },
    )
    assert response.status_code == 202 and response.json()["job_id"] == jid
    assert len(client.get("/api/v1/memories").json()["items"]) == 1
    preview = client.get("/api/v1/memories/" + row["id"] + "/deletion-preview")
    assert preview.json()["delete_original"] is False
    assert (
        write(
            client, "delete", "/api/v1/memories/" + row["id"], {"expected_version": 1}
        ).status_code
        == 422
    )
    response = write(
        client,
        "delete",
        "/api/v1/memories/" + row["id"],
        {"expected_version": 1, "confirmed": True},
    )
    assert response.status_code == 200 and response.json()["status"] == "completed"
    assert client.get("/api/v1/notes/" + note["id"]).status_code == 200
    assert client.get("/api/v1/memories/" + row["id"]).status_code == 404
    with Session(engine(client)) as db:
        fact = db.get(Memory, row["id"])
        assert fact and fact.content == ""
        candidate = db.get(MemoryCandidate, candidates[0]["id"])
        assert candidate and candidate.proposed_content == ""
        assert (
            db.scalar(
                select(func.count())
                .select_from(MemorySuppression)
                .where(MemorySuppression.owner_id == fact.owner_id)
            )
            == 1
        )
    retry = write(
        client,
        "post",
        "/api/v1/memory-candidates",
        {
            "source_refs": [
                {"source_type": "note", "source_id": note["id"], "source_version": note["version"]}
            ]
        },
    )
    assert retry.status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        "unknown_source",
        "assistant_fact",
        "confirmation",
        "empty",
        "bad_json",
        "bad_usage",
        "event_time",
    ],
)
def test_invalid_candidates_never_save(client: TestClient, change: str) -> None:
    note, jid = pending(client)

    async def invoke(messages: list[BaseMessage]) -> AIMessage:
        item = {
            "content": note["body"],
            "claim_type": "user_statement",
            "source_ids": [note["id"]],
            "evidence": note["body"],
            "event_time": None,
        }
        if change == "unknown_source":
            item["source_ids"] = [str(uuid4())]
        if change == "assistant_fact":
            item["content"] = "invented statement"
        if change == "confirmation":
            item["claim_type"] = "confirmed_preference"
        if change == "empty":
            item["content"] = " "
        if change == "event_time":
            item["event_time"] = "2026-10-02T00:00:00Z"
        return AIMessage(
            content="not JSON" if change == "bad_json" else json.dumps({"memories": [item]}),
            usage_metadata={
                "input_tokens": 10,
                "output_tokens": 10,
                "total_tokens": 999 if change == "bad_usage" else 20,
            },
        )

    run(client, jid, invoke=invoke)
    assert state(client, jid)["status"] == "failed"
    assert client.get("/api/v1/memories").json()["items"] == []
    assert client.get("/api/v1/memory-candidates").json()["items"] == []
    assert state(client, jid)["attempt"] == 1


@pytest.mark.parametrize("effect", ["cancel", "revoke", "delete", "edit", "generation"])
def test_late_candidates_rejected(client: TestClient, effect: str) -> None:
    note, jid = pending(client)
    selected = lease(client, jid)

    def phase(value: str) -> None:
        if value != "before_commit":
            return
        if effect == "cancel":
            current = state(client, jid)
            assert (
                client.post(
                    "/api/v1/jobs/" + jid + "/cancel", json={"expected_version": current["version"]}
                ).status_code
                == 200
            )
        elif effect == "delete":
            assert (
                write(
                    client,
                    "delete",
                    "/api/v1/notes/" + note["id"],
                    {"expected_version": 1, "confirmed": True},
                ).status_code
                == 202
            )
        elif effect == "edit":
            assert (
                write(
                    client,
                    "patch",
                    "/api/v1/notes/" + note["id"],
                    {"expected_version": 1, "body": "changed source"},
                ).status_code
                == 200
            )
        else:
            with Session(engine(client)) as db, db.begin():
                job = db.get(BackgroundJob, jid)
                assert job
                if effect == "generation":
                    job.generation += 1
                else:
                    grant = db.get(ContextGrant, str(job.source_refs[0]["grant_ref"]))
                    assert grant
                    grant.revoked_at = jobs.clock(db)

    assert isinstance(client.app, FastAPI)
    asyncio.run(
        memory_worker.execute(engine(client), client.app.state.settings, selected, phase=phase)
    )
    assert state(client, jid)["status"] != "succeeded"
    assert client.get("/api/v1/memories").json()["items"] == []


def test_inference_correction_stop_and_old_version(client: TestClient) -> None:
    note, jid = pending(client)

    async def invoke(messages: list[BaseMessage]) -> AIMessage:
        return AIMessage(
            content=json.dumps(
                {
                    "memories": [
                        {
                            "content": "可能喜欢安静的休息",
                            "claim_type": "system_inference",
                            "evidence": note["body"],
                            "source_ids": [note["id"]],
                        }
                    ]
                }
            )
        )

    run(client, jid, invoke=invoke)
    row = client.get("/api/v1/memories").json()["items"][0]
    assert row["claim_type"] == "system_inference"
    with Session(engine(client)) as db:
        job = db.get(BackgroundJob, jid)
        assert job
        budget = db.get(JobBudget, job.budget_ref)
        assert budget
        assert budget.calls[0]["status"] == "usage_unknown"
        assert budget.calls[0]["charged_tokens"] == budget.calls[0]["reserved_tokens"]
    corrected = write(
        client,
        "patch",
        "/api/v1/memories/" + row["id"],
        {"expected_version": 1, "content": "那只是一次临时安排"},
    )
    assert corrected.status_code == 200 and corrected.json()["claim_type"] == "user_statement"
    assert corrected.json()["correction_id"]
    assert (
        write(
            client,
            "patch",
            "/api/v1/memories/" + row["id"],
            {"expected_version": 1, "content": "旧更正"},
        ).status_code
        == 409
    )
    assert (
        write(
            client,
            "patch",
            "/api/v1/memories/" + row["id"],
            {"expected_version": 2, "status": "stopped"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/memories").json()["items"] == []
    assert len(client.get("/api/v1/memories?status=stopped").json()["items"]) == 1


def test_source_deletion_scrubs_derivatives(client: TestClient) -> None:
    note, jid = pending(client)
    run(client, jid)
    row = client.get("/api/v1/memories").json()["items"][0]
    assert (
        write(
            client,
            "delete",
            "/api/v1/notes/" + note["id"],
            {"expected_version": 1, "confirmed": True},
        ).status_code
        == 202
    )
    response = client.get("/api/v1/memories/" + row["id"]).json()
    assert response["content"] == "" and response["status"] == "needs_review"
    with Session(engine(client)) as db:
        stored = db.get(Memory, row["id"])
        assert stored and not stored.content


def message_source(client: TestClient) -> tuple[str, dict[str, Any]]:
    sid, rid, body = test_runs.create(client)
    test_runs.start(client, rid, body)
    assert execute_one(engine(client))
    turn = current(client, sid)
    return sid, {
        "source_type": "message",
        "source_id": turn["input_id"],
        "source_version": turn["input_version"],
    }


def excerpt_memory(client: TestClient, ref: dict[str, Any]) -> tuple[dict[str, Any], str]:
    enable(client)
    note = saved_note(client, kind="linked_excerpt", body=None, source_refs=[ref])
    response = write(
        client,
        "post",
        "/memory-candidates",
        {"source_refs": [{"source_type": "note", "source_id": note["id"], "source_version": 1}]},
    )
    assert response.status_code == 202, response.text
    jid = response.json()["job_id"]
    run(client, jid)
    assert state(client, jid)["status"] == "succeeded"
    return note, jid


@pytest.mark.parametrize("change", ["retarget", "purge"])
def test_forget_excerpt_suppresses_extracted_message_snapshot(
    client: TestClient, change: str
) -> None:
    _, original = message_source(client)
    _, replacement = message_source(client)
    note, _ = excerpt_memory(client, original)
    row = client.get("/api/v1/memories").json()["items"][0]
    with Session(engine(client)) as db:
        stored = db.get(Memory, row["id"])
        assert stored is not None and stored.source_snapshot == [original]
    if change == "retarget":
        response = write(
            client,
            "patch",
            "/notes/" + note["id"],
            {"expected_version": 1, "source_refs": [replacement]},
        )
        assert response.status_code == 200, response.text
    else:
        response = write(
            client,
            "delete",
            "/notes/" + note["id"],
            {"expected_version": 1, "confirmed": True},
        )
        assert response.status_code == 202, response.text
    response = write(
        client,
        "delete",
        "/memories/" + row["id"],
        {"expected_version": row["version"], "confirmed": True},
    )
    assert response.status_code == 200, response.text
    with Session(engine(client)) as db:
        stored = db.get(Memory, row["id"])
        assert stored is not None
        assert suppressed(db, stored.owner_id, [original])
        assert not suppressed(db, stored.owner_id, [replacement])
        keys = set(
            db.scalars(
                select(MemorySuppression.source_key).where(
                    MemorySuppression.owner_id == stored.owner_id
                )
            )
        )
        assert keys == {source_key(original), source_key(row["source_refs"][0])}
    another = saved_note(client, kind="linked_excerpt", body=None, source_refs=[original])
    response = write(
        client,
        "post",
        "/memory-candidates",
        {
            "source_refs": [
                {
                    "source_type": "note",
                    "source_id": another["id"],
                    "source_version": 1,
                }
            ]
        },
    )
    assert response.status_code == 409 and response.json()["code"] == "memory_source_suppressed"
    excerpt_memory(client, replacement)


@pytest.mark.parametrize(
    "currency,fail_cleanup", [(None, False), ("SYNTHETIC", False), ("USD", False), ("USD", True)]
)
def test_conversation_receipt_includes_linked_excerpt_calls(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, currency: str | None, fail_cleanup: bool
) -> None:
    sid, ref = message_source(client)
    note, jid = excerpt_memory(client, ref)
    with Session(engine(client)) as db, db.begin():
        job = db.get(BackgroundJob, jid)
        assert job is not None
        budget = db.get(JobBudget, job.budget_ref)
        assert budget is not None
        # Synthetic persisted receipt fixture; no external call is made.
        budget.calls = [{**call, "currency": currency} for call in budget.calls] if currency else []
    purge = deletion.purge_step

    def fail(db: Session, job: Any, step: str) -> None:
        raise RuntimeError("synthetic cleanup failure")

    if fail_cleanup:
        monkeypatch.setattr(deletion, "purge_step", fail)
    response = remove(client, sid)
    assert response.status_code == 202, response.text
    receipt = response.json()
    expected = "unknown" if currency == "USD" else "not_applicable"
    assert receipt["external_provider_status"] == expected
    if fail_cleanup:
        assert receipt["status"] == "failed_retryable"
        monkeypatch.setattr(deletion, "purge_step", purge)
        receipt = write(
            client,
            "post",
            "/deletion-jobs/" + receipt["deletion_id"] + "/retry",
            {"expected_version": receipt["version"]},
        ).json()
    assert receipt["status"] == "completed"
    assert receipt["external_provider_status"] == expected
    assert client.get("/api/v1/notes/" + note["id"]).status_code == 404
    reread = client.get("/api/v1/deletion-jobs/" + receipt["deletion_id"]).json()
    assert reread["external_provider_status"] == expected
    assert ("external_provider" in reread["not_applicable"]) == (expected == "not_applicable")


def test_draft_and_foreign_sources_do_not_enqueue(client: TestClient, other: TestClient) -> None:
    enable(client)
    draft = write(
        client,
        "post",
        "/api/v1/notes",
        {"kind": "free", "title": "draft", "body": "draft body", "status": "draft"},
    )

    assert draft.status_code == 201
    assert client.get("/api/v1/jobs").json()["counts"] == {}
    source = saved_note(other)
    assert write(
        client,
        "post",
        "/api/v1/memory-candidates",
        {"source_refs": [{"source_type": "note", "source_id": source["id"], "source_version": 1}]},
    ).status_code in {404, 409}


def test_user_message_can_extract_but_cancelled_assistant_cannot(client: TestClient) -> None:
    from app.models import Message, Run
    from app.records import source_available

    enable(client)
    _, rid, body = test_runs.create(client)
    test_runs.start(client, rid, body)
    with Session(engine(client)) as db, db.begin():
        original = db.scalar(select(Message).where(Message.run_id == rid, Message.role == "user"))
        assert original
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.owner_id == original.owner_id))
        assert job
        jid = job.id
        run_row = db.get(Run, rid)
        assert run_row
        run_row.status = "cancelled"
        assistant = Message(
            owner_id=original.owner_id, run_id=rid, role="assistant", content="partial wording"
        )
        db.add(assistant)
        db.flush()
        for message, expected in ((original, True), (assistant, False)):
            assert (
                source_available(
                    db,
                    ContextGrant(
                        owner_id=message.owner_id,
                        source_type="message",
                        source_id=message.id,
                        source_version=message.version,
                    ),
                )
                is expected
            )
    run(client, jid)
    assert state(client, jid)["status"] == "succeeded"


def test_revoke_while_model_pending_cancels_call(client: TestClient) -> None:
    _, jid = pending(client)
    called = False
    cancelled = False

    async def invoke(messages: list[BaseMessage]) -> AIMessage:
        nonlocal called, cancelled
        called = True
        with Session(engine(client)) as db, db.begin():
            job = db.get(BackgroundJob, jid)
            assert job
            grant = db.get(ContextGrant, str(job.source_refs[0]["grant_ref"]))
            assert grant
            grant.revoked_at = jobs.clock(db)
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled = True
            raise
        return AIMessage(content='{"memories":[]}')

    run(client, jid, invoke=invoke)
    assert called and cancelled and state(client, jid)["status"] == "invalidated"
    assert client.get("/api/v1/memories").json()["items"] == []


@pytest.mark.parametrize("phase", ["after_claim", "before_commit", "after_commit"])
def test_real_killed_memory_worker_recovers_once(
    client: TestClient,
    phase: str,
    tmp_path: Path,
) -> None:
    _, jid = pending(client)
    with Session(engine(client)) as db, db.begin():
        for row in db.scalars(
            select(BackgroundJob).where(
                BackgroundJob.id != jid,
                BackgroundJob.kind == "memory_extraction",
                BackgroundJob.status.in_(jobs.ACTIVE),
            )
        ):
            jobs.finish(row, "cancelled", "test_cleanup", jobs.clock(db))
    log = tmp_path / "worker.txt"
    command = [sys.executable, "-m", "app.worker", "--memory"]
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [*command, "--probe-pause", phase],
            env={**child_env(), "PSYEVO_MEMORY_MODE": "fake"},
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while "memory.probe_pause phase=" + phase not in log.read_text(encoding="utf-8"):
                assert process.poll() is None, log.read_text(encoding="utf-8")
                assert time.monotonic() < deadline, log.read_text(encoding="utf-8")
                time.sleep(0.05)
            process.kill()
            process.wait(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    before = state(client, jid)
    # A fresh OS process owns recovery; the original lease expires using the real PG clock.
    recovered = subprocess.Popen(
        command,
        env={**child_env(), "PSYEVO_MEMORY_MODE": "fake"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 20
        while state(client, jid)["status"] != "succeeded":
            assert recovered.poll() is None
            assert time.monotonic() < deadline, state(client, jid)
            time.sleep(0.1)
    finally:
        recovered.kill()
        recovered.communicate(timeout=10)
    after = state(client, jid)
    assert after["attempt"] == (1 if phase == "after_commit" else 2)
    assert after["lease_token"] == (
        before["lease_token"] if phase == "after_commit" else before["lease_token"] + 1
    )
    with Session(engine(client)) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(MemoryCandidate)
                .where(MemoryCandidate.job_id == jid)
            )
            == 1
        )
        stored_job = db.get(BackgroundJob, jid)
        assert stored_job
        row = stored_job
        account = db.get(JobBudget, row.budget_ref)
        assert account is not None
        assert len(account.calls) == (2 if phase == "before_commit" else 1)
        if phase == "before_commit":
            assert account.calls[0]["status"] == "reserved"
            assert account.calls[0]["actual_tokens"] is None
    evidence_dir = os.environ.get("PSYEVO_S2_STEP04_ARTIFACTS")
    if evidence_dir:
        Path(evidence_dir, "memory-crash-" + phase + ".json").write_text(
            json.dumps(
                {
                    "case_id": "S2-A10",
                    "execution_kind": "real-postgresql-process-kill/fake-model",
                    "phase": phase,
                    "job_id": jid,
                    "before": before,
                    "after": after,
                    "calls": account.calls,
                    "result_count": 1,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
