"""S2-A09/A10: real PG transactions and killed standalone Workers, synthetic inputs."""

import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pydantic import SecretStr
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app import job_worker, jobs
from app.api import APIError
from app.config import Settings
from app.models import BackgroundJob, ContextGrant, Idempotency, JobBudget, Note, User
from app.security import digest
from app.support import Budget
from tests import test_runs
from tests.test_records import saved_note, write
from tests.test_runs import engine
from tests.test_support import ScriptedModel, message

client = test_runs.client
other = test_runs.client
pytestmark = pytest.mark.postgres


def settings() -> Settings:
    return Settings(
        environment="test",
        support_mode="fake",
        database_url=SecretStr(os.environ["PSYEVO_TEST_DATABASE_URL"]),
    )


def enqueue(db: Session, owner: str, source: dict[str, Any], **kw: Any) -> BackgroundJob:
    return jobs.enqueue(
        db,
        settings(),
        owner,
        [
            jobs.JobSource(
                source_type="note",
                source_id=source["id"],
                source_version=source["version"],
            )
        ],
        budget=Budget(deadline_seconds=120),
        **kw,
    )


@pytest.fixture
def job(client: TestClient) -> Iterator[tuple[str, str, dict[str, Any]]]:
    source = saved_note(client)
    with Session(engine(client)) as db, db.begin():
        note = db.get(Note, source["id"])
        assert note is not None
        owner = note.owner_id
        row = enqueue(db, owner, source)
        jid = row.id
    try:
        yield jid, owner, source
    finally:
        with Session(engine(client)) as db, db.begin():
            for row in db.scalars(select(BackgroundJob).where(BackgroundJob.owner_id == owner)):
                if row.status in jobs.ACTIVE:
                    jobs.finish(row, "cancelled", "test_cleanup", jobs.clock(db))


def claim(client: TestClient, jid: str) -> jobs.Lease:
    result = jobs.claim(engine(client), str(uuid4()))
    assert result is not None and result.job_id == jid
    return result


def state(client: TestClient, jid: str) -> dict[str, Any]:
    result = client.get("/api/v1/jobs/" + jid)
    assert result.status_code == 200, result.text
    return dict(result.json())


def ready_again(client: TestClient, jid: str) -> None:
    with Session(engine(client)) as db, db.begin():
        row = db.get(BackgroundJob, jid)
        assert row is not None
        row.available_at = jobs.clock(db) - timedelta(seconds=1)


def test_enqueue_atomic_dedupe_owner_and_purpose(
    client: TestClient,
    other: TestClient,
    job: tuple[str, str, dict[str, Any]],
) -> None:
    jid, owner, source = job
    with Session(engine(client)) as db, db.begin():
        assert enqueue(db, owner, source).id == jid
        row = db.get(BackgroundJob, jid)
        assert row is not None
        grant_id = str(row.source_refs[0]["grant_ref"])
        grant = db.get(ContextGrant, grant_id)
        assert grant is not None and grant.run_id is None
    assert client.get("/api/v1/context-grants/" + grant_id).json()["active"]
    assert other.get("/api/v1/jobs/" + jid).status_code == 404
    assert other.get("/api/v1/jobs").json()["counts"] == {}
    summary = client.get("/api/v1/jobs").json()
    assert summary["counts"] == {"queued": 1} and summary["oldest_wait_seconds"] >= 0
    assert (
        other.post("/api/v1/jobs/" + jid + "/cancel", json={"expected_version": 1}).status_code
        == 404
    )
    stranger = saved_note(other)
    with pytest.raises(APIError), Session(engine(client)) as db, db.begin():
        enqueue(db, owner, stranger)
    with pytest.raises(RuntimeError), Session(engine(client)) as db, db.begin():
        extra = Note(owner_id=owner, body="must roll back", kind="free", status="saved")
        db.add(extra)
        db.flush()
        extra_id = extra.id
        enqueue(db, owner, {"id": extra.id, "version": 1})
        raise RuntimeError("after_source_before_commit")
    with Session(engine(client)) as db:
        assert db.get(Note, extra_id) is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(BackgroundJob)
                .where(BackgroundJob.owner_id == owner)
            )
            == 1
        )
        assert "memories" not in inspect(engine(client)).get_table_names()


def test_concurrent_claim_and_fencing(
    client: TestClient, job: tuple[str, str, dict[str, Any]]
) -> None:
    jid, _, _ = job
    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(lambda _: jobs.claim(engine(client), str(uuid4())), range(2)))
    assert sum(lease is not None for lease in leases) == 1
    lease = next(lease for lease in leases if lease is not None)
    token = lease.token
    assert jobs.renew(engine(client), lease, lease_seconds=10)
    assert state(client, jid)["lease_token"] == token
    request_id = jobs.reserve(engine(client), lease, 100)
    assert request_id is not None
    assert not jobs.complete(
        engine(client), replace(lease, token=token - 1), request_id, 20, job_worker.commit_probe
    )
    with Session(engine(client)) as db, db.begin():
        row = db.get(BackgroundJob, jid)
        assert row is not None
        row.lease_until = jobs.clock(db) - timedelta(seconds=1)
    assert not jobs.renew(engine(client), lease)
    assert jobs.claim(engine(client), "reclaimer") is None
    assert state(client, jid)["status"] == "retry_wait"
    ready_again(client, jid)
    current = claim(client, jid)
    assert current.token > token
    assert not jobs.complete(engine(client), lease, request_id, 20, job_worker.commit_probe)
    assert not jobs.fail(engine(client), lease, "schema")
    request2 = jobs.reserve(engine(client), current, 100)
    assert request2 is not None
    assert jobs.complete(engine(client), current, request2, 20, job_worker.commit_probe)
    assert not jobs.complete(engine(client), current, request2, 20, job_worker.commit_probe)
    assert state(client, jid)["attempt"] == 2


@pytest.mark.parametrize("blocked_count", [100, 201])
def test_claim_scans_past_locked_owner_batches(
    client: TestClient,
    other: TestClient,
    job: tuple[str, str, dict[str, Any]],
    blocked_count: int,
) -> None:
    jid, _, _ = job
    source = saved_note(other)
    with Session(engine(client)) as db, db.begin():
        note = db.get(Note, source["id"])
        assert note is not None
        blocked_owner = note.owner_id
        at = jobs.clock(db) - timedelta(seconds=2)
        blocked_ids = []
        for _ in range(blocked_count):
            note = Note(
                owner_id=blocked_owner, body="synthetic queued source", kind="free", status="saved"
            )
            db.add(note)
            db.flush()
            row = enqueue(db, blocked_owner, {"id": note.id, "version": note.version})
            # Equal timestamps require the pagination cursor to include the job ID.
            row.available_at = at
            blocked_ids.append(row.id)
        target = db.get(BackgroundJob, jid)
        assert target is not None
        target.available_at = at + timedelta(seconds=1)
    try:
        with Session(engine(client)) as locked, locked.begin():
            locked.scalar(select(User.id).where(User.id == blocked_owner).with_for_update())
            lease = jobs.claim(engine(client), "unblocked-owner", lease_seconds=60)
            assert lease is not None and lease.job_id == jid
            assert jobs.claim(engine(client), "only-locked-owners") is None
            with Session(engine(client)) as db:
                blocked = db.scalars(
                    select(BackgroundJob).where(BackgroundJob.id.in_(blocked_ids))
                ).all()
                assert len(blocked) == blocked_count
                assert all(row.status == "queued" and row.attempt == 0 for row in blocked)
        lease = jobs.claim(engine(client), "owner-unlocked")
        assert lease is not None and lease.job_id in blocked_ids
    finally:
        with Session(engine(client)) as db, db.begin():
            for row in db.scalars(select(BackgroundJob).where(BackgroundJob.id.in_(blocked_ids))):
                jobs.finish(row, "cancelled", "test_cleanup", jobs.clock(db))


def test_probe_rejects_note_api_receipt_collision(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
) -> None:
    jid, owner, _ = job
    key = "job-probe:" + jid
    body = {"body": "synthetic unrelated note"}
    response = write(client, "POST", "/notes", body, key)
    assert response.status_code == 201, response.text
    note_id = response.json()["id"]
    assert job_worker.execute_one(engine(client), settings(), "receipt-collision")
    result = state(client, jid)
    assert result["status"] == "failed" and result["error_code"] == "schema"
    assert result["result_ref"] is None and result["attempt"] == 1
    assert not job_worker.execute_one(engine(client), settings(), "no-retry")
    assert write(client, "POST", "/notes", body, key).json()["id"] == note_id
    with Session(engine(client)) as db:
        receipt = db.get(Idempotency, (owner, key))
        assert receipt is not None and receipt.resource_type == "Note"
        assert receipt.resource_id == note_id


@pytest.mark.parametrize("mismatch", [None, "resource_type", "resource_id", "request_hash"])
def test_probe_validates_existing_receipt(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
    mismatch: str | None,
) -> None:
    jid, owner, _ = job
    expected = {"resource_type": "job_probe", "resource_id": jid, "request_hash": digest(jid)}
    if mismatch:
        expected[mismatch] = {
            "resource_type": "Note",
            "resource_id": str(uuid4()),
            "request_hash": digest("different"),
        }[mismatch]
    with Session(engine(client)) as db, db.begin():
        db.add(Idempotency(owner_id=owner, key="job-probe:" + jid, **expected))
    assert job_worker.execute_one(engine(client), settings(), "existing-receipt")
    result = state(client, jid)
    assert result["status"] == ("failed" if mismatch else "succeeded")
    assert result["error_code"] == ("schema" if mismatch else None)
    assert result["result_ref"] == (None if mismatch else jid)
    assert not job_worker.execute_one(engine(client), settings(), "no-replay")
    with Session(engine(client)) as db:
        receipt = db.get(Idempotency, (owner, "job-probe:" + jid))
        assert receipt is not None
        assert {field: getattr(receipt, field) for field in expected} == expected


def test_job_grants_do_not_remove_normal_chat_history(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
) -> None:
    from app.history import context_history
    from app.models import Run
    from app.run_worker import execute_one
    from tests.test_multiturn import send
    from tests.test_support import request

    sid, rid, body = test_runs.create(client)
    test_runs.start(client, rid, body)
    assert execute_one(engine(client))
    current_id = send(client, sid, "synthetic next turn")
    with Session(engine(client)) as db:
        current_run = db.get(Run, current_id)
        assert current_run is not None
        turns = context_history(db, current_run, request(), Budget())
        assert [turn.run_id for turn in turns] == [rid]


@pytest.mark.parametrize("change", ["revoke", "delete", "edit", "cancel", "config", "generation"])
def test_invalidation_blocks_late_read_and_commit(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
    change: str,
) -> None:
    jid, owner, source = job
    lease = claim(client, jid)
    request_id = jobs.reserve(engine(client), lease, 100)
    assert request_id is not None
    if change == "revoke":
        with Session(engine(client)) as db:
            row = db.get(BackgroundJob, jid)
            assert row is not None
            gid = str(row.source_refs[0]["grant_ref"])
        result = client.request(
            "DELETE", "/api/v1/context-grants/" + gid, json={"expected_version": 1}
        )
        assert result.status_code == 200
    elif change == "delete":
        assert (
            write(
                client,
                "DELETE",
                "/notes/" + source["id"],
                {"expected_version": 1, "confirmed": True},
            ).status_code
            == 202
        )
    elif change == "edit":
        assert (
            write(
                client,
                "PATCH",
                "/notes/" + source["id"],
                {"expected_version": 1, "body": "changed"},
            ).status_code
            == 200
        )
    elif change == "cancel":
        current = state(client, jid)
        assert (
            client.post(
                "/api/v1/jobs/" + jid + "/cancel", json={"expected_version": current["version"]}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/jobs/" + jid + "/cancel", json={"expected_version": current["version"]}
            ).json()["status"]
            == "cancelled"
        )
    else:
        with Session(engine(client)) as db, db.begin():
            row = db.get(BackgroundJob, jid)
            assert row is not None
            if change == "config":
                row.experiment_config_version = "old-config/0"
            else:
                replacement = enqueue(db, owner, source, generation=2)
                assert replacement.budget_ref == row.budget_ref
                assert replacement.deadline_at == row.deadline_at
                assert replacement.attempt == row.attempt
    assert not jobs.renew(engine(client), lease)
    assert jobs.reserve(engine(client), lease, 10) is None
    assert not jobs.complete(engine(client), lease, request_id, 20, job_worker.commit_probe)
    assert state(client, jid)["status"] in {"cancelled", "invalidated"}
    with Session(engine(client)) as db:
        assert db.get(Idempotency, (owner, "job-probe:" + jid)) is None


@pytest.mark.parametrize(
    "code,retries",
    [
        ("temporary_io", True),
        ("timeout", True),
        ("schema", False),
        ("parameters", False),
        ("permission", False),
        ("deleted", False),
        ("unknown_mutation", False),
        ("PRIVATE exception body", False),
    ],
)
def test_retry_classification_and_attempt_limit(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
    code: str,
    retries: bool,
) -> None:
    jid, _, _ = job
    lease = claim(client, jid)
    assert jobs.fail(engine(client), lease, code)
    result = state(client, jid)
    assert result["status"] == ("retry_wait" if retries else "failed")
    assert "PRIVATE" not in json.dumps(result)
    if retries:
        for _ in range(2):
            ready_again(client, jid)
            assert jobs.fail(engine(client), claim(client, jid), code)
        result = state(client, jid)
        assert result["status"] == "failed" and result["attempt"] == 3
        assert jobs.claim(engine(client), "after_limit") is None


def test_reservations_survive_generation_and_exhaustion(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
) -> None:
    jid, owner, source = job
    lease = claim(client, jid)
    assert jobs.reserve(engine(client), lease, 5000)
    with Session(engine(client)) as db, db.begin():
        replacement = enqueue(db, owner, source, generation=2)
        new_id = replacement.id
    new_lease = claim(client, new_id)
    assert jobs.reserve(engine(client), new_lease, 4000) is None
    assert state(client, new_id)["error_code"] == "budget_exhausted"
    with Session(engine(client)) as db:
        row = db.get(BackgroundJob, new_id)
        assert row is not None
        account = db.get(JobBudget, row.budget_ref)
        assert account is not None and account.calls[0]["charged_tokens"] == 5000


def test_commit_storage_failure_and_unknown_ack(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
) -> None:
    jid, owner, _ = job
    lease = claim(client, jid)
    request_id = jobs.reserve(engine(client), lease, 100)
    assert request_id is not None

    def broken(db: Session, row: BackgroundJob) -> str:
        job_worker.commit_probe(db, row)
        db.flush()
        # Kill this transaction's real PostgreSQL connection before commit.
        db.execute(text("SELECT pg_terminate_backend(pg_backend_pid())"))
        raise AssertionError("The terminated connection must not return")

    with pytest.raises(OperationalError):
        jobs.complete(engine(client), lease, request_id, 20, broken)
    with Session(engine(client)) as db:
        assert db.get(Idempotency, (owner, "job-probe:" + jid)) is None
    assert state(client, jid)["status"] == "running"
    assert jobs.complete(engine(client), lease, request_id, 20, job_worker.commit_probe)
    # Simulated lost reply after commit: reconciliation sees succeeded; no new claim/effect.
    assert jobs.claim(engine(client), "duplicate_notification") is None
    with Session(engine(client)) as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Idempotency).where(Idempotency.resource_id == jid)
            )
            == 1
        )


def test_deadline_and_old_lease_during_transaction(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
) -> None:
    jid, owner, _ = job
    lease = claim(client, jid)
    request_id = jobs.reserve(engine(client), lease, 100)
    assert request_id is not None

    def expires(db: Session, row: BackgroundJob) -> str:
        result = job_worker.commit_probe(db, row)
        row.lease_until = jobs.clock(db) - timedelta(seconds=1)
        return result

    assert not jobs.complete(engine(client), lease, request_id, 20, expires)
    with Session(engine(client)) as db, db.begin():
        assert db.get(Idempotency, (owner, "job-probe:" + jid)) is None
        row = db.get(BackgroundJob, jid)
        assert row is not None
        row.deadline_at = jobs.clock(db) - timedelta(seconds=1)
        row.lease_until = row.deadline_at
    jobs.claim(engine(client), "expired")
    assert state(client, jid)["error_code"] == "deadline"


def test_probe_validates_schema_and_reads_real_source(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
) -> None:
    jid, _, _ = job
    adapter = ScriptedModel(responses=[], outcomes=[message("invalid candidate")])
    asyncio.run(job_worker.execute(engine(client), claim(client, jid), model=adapter))
    assert state(client, jid)["error_code"] == "schema"
    assert "synthetic private note" in str(adapter.captures)
    assert "memory_candidates" not in inspect(engine(client)).get_table_names()


@pytest.mark.parametrize("revoke", [False, True])
def test_worker_renews_and_cancels_in_flight(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
    revoke: bool,
) -> None:
    jid, _, _ = job
    adapter = ScriptedModel(
        responses=[],
        outcomes=[
            AIMessage(
                content='{"probe":"recovery-probe/1","source_count":1}',
                usage_metadata={"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
            )
        ],
        delay=5.2 if not revoke else 2,
    )
    lease = claim(client, jid)

    async def run() -> None:
        task = asyncio.create_task(job_worker.execute(engine(client), lease, model=adapter))
        for _ in range(100):
            if adapter.calls:
                break
            await asyncio.sleep(0.01)
        assert adapter.calls == 1
        if revoke:
            with Session(engine(client)) as db, db.begin():
                row = db.get(BackgroundJob, jid)
                assert row is not None
                grant = db.get(ContextGrant, str(row.source_refs[0]["grant_ref"]))
                assert grant is not None
                grant.revoked_at = jobs.clock(db)
                grant.version += 1
        await task

    asyncio.run(run())
    result = state(client, jid)
    assert result["status"] == ("invalidated" if revoke else "succeeded")
    assert result["attempt"] == 1 and result["lease_losses"] == 0
    assert adapter.calls == 1


def test_unknown_usage_is_charged_and_total_calls_are_bounded(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
) -> None:
    jid, _, _ = job
    lease = claim(client, jid)
    first = jobs.reserve(engine(client), lease, 100)
    assert first is not None
    assert jobs.fail(engine(client), lease, "temporary_io")
    ready_again(client, jid)
    second_lease = claim(client, jid)
    second = jobs.reserve(engine(client), second_lease, 100)
    assert second is not None
    assert jobs.fail(engine(client), second_lease, "temporary_io")
    ready_again(client, jid)
    third_lease = claim(client, jid)
    assert jobs.reserve(engine(client), third_lease, 1) is None
    assert state(client, jid)["error_code"] == "budget_exhausted"


def child_env() -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper()
        in {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "PYTHONPATH",
            "PSYEVO_CHECK_NETWORK",
        }
    }
    env.update(
        PSYEVO_ENV="test",
        PSYEVO_SUPPORT_MODE="fake",
        PYTHONUTF8="1",
        PSYEVO_DATABASE_URL=os.environ["PSYEVO_TEST_DATABASE_URL"],
    )
    return env


@pytest.mark.parametrize("phase", ["after_claim", "before_commit", "after_commit"])
def test_real_killed_worker_recovers_once(
    client: TestClient,
    job: tuple[str, str, dict[str, Any]],
    phase: str,
    tmp_path: Path,
) -> None:
    jid, owner, _ = job
    log = tmp_path / "worker.txt"
    command = [sys.executable, "-m", "app.worker", "--jobs-probe"]
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            [*command, "--probe-pause", phase],
            env=child_env(),
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while "job.probe_pause phase=" + phase not in log.read_text(encoding="utf-8"):
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
        command, env=child_env(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
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
                select(func.count()).select_from(Idempotency).where(Idempotency.resource_id == jid)
            )
            == 1
        )
        row = db.get(BackgroundJob, jid)
        assert row is not None
        account = db.get(JobBudget, row.budget_ref)
        assert account is not None
        assert len(account.calls) == (2 if phase == "before_commit" else 1)
        if phase == "before_commit":
            assert account.calls[0]["status"] == "reserved"
            assert account.calls[0]["actual_tokens"] is None
    evidence_dir = os.environ.get("PSYEVO_S2_STEP03_ARTIFACTS")
    if evidence_dir:
        Path(evidence_dir, "crash-" + phase + ".json").write_text(
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


def test_database_unavailable_is_bounded(tmp_path: Path) -> None:
    env = child_env()
    # A closed loopback port, never a real service or the development DB.
    env["PSYEVO_DATABASE_URL"] = (
        "postgresql+psycopg://fake:fake@127.0.0.1:1/psyevo_synthetic_check?connect_timeout=1"
    )
    result = subprocess.run(
        [sys.executable, "-m", "app.worker", "--jobs-probe"],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert result.stdout.count("job.database_unavailable") == 3
    assert "fake:fake" not in result.stderr


def test_job_grant_and_budget_database_owner_constraints(
    client: TestClient,
    other: TestClient,
    job: tuple[str, str, dict[str, Any]],
) -> None:
    jid, _, _ = job
    foreign = saved_note(other)
    with Session(engine(client)) as db:
        source = db.get(Note, foreign["id"])
        assert source is not None
        foreign_owner = source.owner_id
    with pytest.raises(IntegrityError), Session(engine(client)) as db, db.begin():
        db.execute(
            text("UPDATE context_grants SET owner_id=:owner WHERE job_id=:jid"),
            {"owner": foreign_owner, "jid": jid},
        )
    with pytest.raises(IntegrityError), Session(engine(client)) as db, db.begin():
        db.execute(
            text("UPDATE background_jobs SET owner_id=:owner WHERE id=:jid"),
            {"owner": foreign_owner, "jid": jid},
        )
