"""S2-STEP02 actual PostgreSQL/API/Support graph, synthetic data only."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import deletion
from app.models import ContextGrant, Note, Run, SleepRecord, SupportCard
from app.run_worker import claim, execute, execute_one
from tests import test_runs
from tests.test_history import current, post, remove
from tests.test_runs import create, engine, start
from tests.test_support import ScriptedModel, message

client = test_runs.client
other = test_runs.client
pytestmark = pytest.mark.postgres


def write(
    client: TestClient, method: str, path: str, body: dict[str, Any], key: str | None = None
) -> Any:
    return client.request(
        method, "/api/v1" + path, json=body, headers={"Idempotency-Key": key or uuid4().hex}
    )


def saved_note(client: TestClient, **fields: Any) -> dict[str, Any]:
    response = post(client, "/notes", {"body": "synthetic private note", **fields})
    assert response.status_code == 201, response.text
    return dict(response.json())


def grant(client: TestClient, rid: str, row: dict[str, Any], kind: str = "note") -> dict[str, Any]:
    response = post(
        client,
        "/context-grants",
        {
            "run_id": rid,
            "source_type": kind,
            "source_id": row["id"],
            "source_version": row["version"],
            "purpose": "current_run",
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def test_notes_drafts_retry_conflict_and_owner(client: TestClient, other: TestClient) -> None:
    key = uuid4().hex
    body = {"title": "synthetic", "body": "private draft", "status": "draft"}
    first = post(client, "/notes", body, key)
    assert first.status_code == 201, first.text
    row = first.json()
    assert post(client, "/notes", body, key).json()["id"] == row["id"]
    assert post(client, "/notes", {**body, "body": "changed"}, key).status_code == 409
    assert other.get(f"/api/v1/notes/{row['id']}").status_code == 404
    assert other.get(f"/api/v1/record-requests/{key}").status_code == 404
    assert client.get(f"/api/v1/record-requests/{key}").json()["committed"]
    _, rid, _ = create(client)
    assert (
        post(
            client,
            "/context-grants",
            {
                "run_id": rid,
                "source_type": "note",
                "source_id": row["id"],
                "source_version": 1,
                "purpose": "current_run",
            },
        ).status_code
        == 409
    )
    edit = {**body, "body": "saved version", "status": "saved", "expected_version": 1}
    edit_key = uuid4().hex
    result = write(client, "PATCH", f"/notes/{row['id']}", edit, edit_key)
    assert result.status_code == 200, result.text
    assert result.json()["version"] == 2
    assert write(client, "PATCH", f"/notes/{row['id']}", edit, edit_key).json()["version"] == 2
    assert write(client, "PATCH", f"/notes/{row['id']}", edit).status_code == 409
    assert post(client, "/notes", {"body": " "}).status_code == 422
    assert post(client, "/notes", {"body": "secret", "owner_id": "forged"}).status_code == 422
    with Session(engine(client)) as db:
        assert db.scalar(select(func.count()).select_from(Note).where(Note.id == row["id"])) == 1
        saved = db.get(Note, row["id"])
        assert saved is not None and saved.body == "saved version"


@pytest.mark.parametrize(
    "occurred_at,timezone,day,other_day",
    [
        ("2026-09-30T00:30:00+08:00", "Asia/Shanghai", "2026-09-30", "2026-09-29"),
        ("2026-09-29T23:30:00-04:00", "America/New_York", "2026-09-29", "2026-09-30"),
        ("2026-11-01T01:30:00-05:00", "America/New_York", "2026-11-01", "2026-10-31"),
        ("2026-09-30T00:30:00+08:00", None, "2026-09-29", "2026-09-30"),
    ],
)
def test_note_date_filter_uses_record_timezone(
    client: TestClient, occurred_at: str, timezone: str | None, day: str, other_day: str
) -> None:
    row = saved_note(client, occurred_at=occurred_at, timezone=timezone)
    saved_note(client)  # Undated records do not match a date filter.
    result = client.get("/api/v1/notes", params={"date": day})
    assert result.status_code == 200, result.text
    assert [item["id"] for item in result.json()["items"]] == [row["id"]]
    assert client.get("/api/v1/notes", params={"date": other_day}).json()["items"] == []


@pytest.mark.parametrize(
    "fields,span",
    [
        (
            {
                "bed_at": "2026-09-29T23:00:00+08:00",
                "wake_at": "2026-09-30T07:00:00+08:00",
                "timezone": "Asia/Shanghai",
            },
            480,
        ),
        (
            {
                "bed_at": "2026-09-30T13:00:00+08:00",
                "wake_at": "2026-09-30T13:40:00+08:00",
                "timezone": "Asia/Shanghai",
            },
            40,
        ),
        ({}, None),
        ({"bed_at": "2026-09-30T23:00:00+08:00", "timezone": "Asia/Shanghai"}, None),
        (
            {
                "bed_at": "2026-11-01T01:30:00-04:00",
                "wake_at": "2026-11-01T01:30:00-05:00",
                "timezone": "America/New_York",
            },
            60,
        ),
        (
            {
                "bed_at": "2026-10-31T23:00:00-04:00",
                "wake_at": "2026-11-01T07:00:00-05:00",
                "timezone": "America/New_York",
            },
            540,
        ),
        (
            {
                "bed_at": "2026-03-07T23:00:00-05:00",
                "wake_at": "2026-03-08T07:00:00-04:00",
                "timezone": "America/New_York",
            },
            420,
        ),
    ],
)
def test_sleep_time_semantics(client: TestClient, fields: dict[str, Any], span: int | None) -> None:
    key = uuid4().hex
    body = {"entry_date": "2026-09-30", **fields}
    result = post(client, "/sleep-records", body, key)
    assert result.status_code == 201, result.text
    row = result.json()
    assert row["span_minutes"] == span
    assert row["interruptions"] is None
    assert post(client, "/sleep-records", body, key).json()["id"] == row["id"]
    assert client.get(f"/api/v1/sleep-records/{row['id']}").json() == row
    changed = write(
        client,
        "PATCH",
        f"/sleep-records/{row['id']}",
        {"expected_version": row["version"], "feeling": "synthetic feeling-only edit"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["span_minutes"] == span
    assert client.get(f"/api/v1/sleep-records/{row['id']}").json() == changed.json()
    with Session(engine(client)) as db:
        saved = db.get(SleepRecord, row["id"])
        assert saved is not None and saved.timezone == fields.get("timezone")


def test_sleep_patch_rejects_reversed_instants_in_repeated_hour(client: TestClient) -> None:
    row = post(
        client,
        "/sleep-records",
        {
            "entry_date": "2026-11-01",
            "bed_at": "2026-11-01T01:15:00-05:00",
            "wake_at": "2026-11-01T02:30:00-05:00",
            "timezone": "America/New_York",
        },
    ).json()
    changed = write(
        client,
        "PATCH",
        f"/sleep-records/{row['id']}",
        {"expected_version": row["version"], "wake_at": "2026-11-01T01:45:00-04:00"},
    )
    assert changed.status_code == 422, changed.text
    assert client.get(f"/api/v1/sleep-records/{row['id']}").json() == row


@pytest.mark.parametrize(
    "fields",
    [
        {"entry_date": "2026-02-30"},
        {"bed_at": "2026-09-30T23:00:00+08:00"},
        {"timezone": "Invented/Zone"},
        {"bed_at": "2026-09-30T23:00:00", "timezone": "Asia/Shanghai"},
        {
            "bed_at": "2026-09-30T23:00:00+08:00",
            "wake_at": "2026-09-30T07:00:00+08:00",
            "timezone": "Asia/Shanghai",
        },
        {"bed_at": "2026-03-08T02:30:00-05:00", "timezone": "America/New_York"},
        {"interruptions": -1},
        {"health_score": 100},
    ],
)
def test_invalid_sleep_never_saved(client: TestClient, fields: dict[str, Any]) -> None:
    result = post(client, "/sleep-records", {"entry_date": "2026-09-30", **fields})
    assert result.status_code == 422, result.text
    assert client.get("/api/v1/sleep-records").json()["items"] == []


def test_sleep_concurrent_versions_and_deletion(client: TestClient, other: TestClient) -> None:
    row = post(client, "/sleep-records", {"entry_date": "2026-09-30"}).json()
    body = {"entry_date": "2026-09-30", "note": "updated", "expected_version": 1}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: write(client, "PATCH", f"/sleep-records/{row['id']}", body), range(2)
            )
        )
    assert sorted(response.status_code for response in results) == [200, 409]
    assert other.get(f"/api/v1/sleep-records/{row['id']}").status_code == 404
    assert (
        write(client, "DELETE", f"/sleep-records/{row['id']}", {"expected_version": 2}).status_code
        == 422
    )
    deleted = write(
        client, "DELETE", f"/sleep-records/{row['id']}", {"expected_version": 2, "confirmed": True}
    )
    assert deleted.status_code == 202 and deleted.json()["status"] == "completed", deleted.text
    assert client.get(f"/api/v1/sleep-records/{row['id']}").status_code == 404
    with Session(engine(client)) as db:
        saved = db.get(SleepRecord, row["id"])
        assert saved is not None and saved.note == "" and saved.entry_date is None


def test_card_singleton_previous_conflict_clear(client: TestClient, other: TestClient) -> None:
    assert client.get("/api/v1/support-card").json()["version"] == 0
    row = write(
        client,
        "PUT",
        "/support-card",
        {"expected_version": 0, "helpful_methods": "synthetic reminder"},
    )
    assert row.status_code == 200, row.text
    assert row.json()["contact_notes"] == ""
    assert write(client, "PUT", "/support-card", {"expected_version": 0}).status_code == 409
    assert (
        write(
            client,
            "PUT",
            "/support-card",
            {"expected_version": 1, "resource_refs": [{"id": "unknown"}]},
        ).status_code
        == 422
    )
    edited = write(client, "PUT", "/support-card", {"expected_version": 1, "self_reminders": "new"})
    assert edited.status_code == 200
    assert edited.json()["previous_content"]["helpful_methods"] == "synthetic reminder"
    assert other.get("/api/v1/support-card").json()["version"] == 0
    key = uuid4().hex
    payload = {"expected_version": 2, "confirmed": True}
    cleared = write(client, "DELETE", "/support-card", payload, key)
    assert cleared.status_code == 202 and cleared.json()["status"] == "completed", cleared.text
    assert (
        write(client, "DELETE", "/support-card", payload, key).json()["deletion_id"]
        == cleared.json()["deletion_id"]
    )
    empty = client.get("/api/v1/support-card").json()
    assert empty["previous_content"] is None and empty["self_reminders"] == ""
    restored = write(
        client,
        "PUT",
        "/support-card",
        {"expected_version": empty["version"], "helpful_methods": "fresh"},
    )
    assert restored.status_code == 200, restored.text
    with Session(engine(client)) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(SupportCard)
                .where(SupportCard.id == row.json()["id"])
            )
            == 1
        )


def test_excerpt_revision_delete_and_no_copied_body(client: TestClient, other: TestClient) -> None:
    sid, rid, body = create(client)
    start(client, rid, body)
    assert execute_one(engine(client))
    turn = current(client, sid)
    ref = {
        "source_type": "message",
        "source_id": turn["input_id"],
        "source_version": turn["input_version"],
    }
    payload = {"kind": "linked_excerpt", "source_refs": [ref], "annotation": "synthetic annotation"}
    assert post(other, "/notes", payload).status_code == 404
    assert post(client, "/notes", {**payload, "body": "permanent copy"}).status_code == 422
    excerpt = post(client, "/notes", payload)
    assert excerpt.status_code == 201, excerpt.text
    note = excerpt.json()
    assert (
        note["body"] is None and note["source_messages"][0]["content"] == body["input"]["message"]
    )
    free = saved_note(client)
    preview = client.get(f"/api/v1/sessions/{sid}/deletion-preview").json()
    assert [row["id"] for row in preview["linked_notes"]] == [note["id"]]
    revised = post(
        client,
        f"/sessions/{sid}/messages/{turn['input_id']}/revisions",
        {"expected_version": turn["input_version"], "content": "revised synthetic"},
    )
    assert revised.status_code == 201, revised.text
    checked = client.get(f"/api/v1/notes/{note['id']}").json()
    assert checked["status"] == "needs_review" and checked["source_messages"] == []
    assert remove(client, sid).json()["status"] == "completed"
    assert client.get(f"/api/v1/notes/{note['id']}").status_code == 404
    assert client.get(f"/api/v1/notes/{free['id']}").status_code == 200
    assert post(client, "/notes", payload).status_code == 404
    with Session(engine(client)) as db:
        row = db.get(Note, note["id"])
        assert row is not None
        assert row.body is None and row.annotation == "" and row.source_refs == []


def test_selected_record_reaches_actual_model_only_once(client: TestClient) -> None:
    row = saved_note(client, body="SELECTED-SYNTHETIC-ONLY")
    saved_note(client, body="UNSELECTED-SYNTHETIC")
    sid, rid, body = create(client)
    g = grant(client, rid, row)
    body["grant_ids"] = [g["id"]]
    start(client, rid, body)
    claimed = claim(engine(client))
    assert claimed and claimed[0] == rid
    model = ScriptedModel(cache=False, responses=[], outcomes=[message("已阅读这次资料。")])
    asyncio.run(execute(engine(client), *claimed, model=model))
    captured = str(model.captures)
    assert "SELECTED-SYNTHETIC-ONLY" in captured and "UNSELECTED-SYNTHETIC" not in captured
    assert client.get(f"/api/v1/context-grants/{g['id']}").json()["active"] is False
    draft = post(
        client,
        "/run-drafts",
        {"context_type": "conversation", "session_id": sid, "expected_session_version": 1},
    ).json()
    start(
        client,
        draft["run_id"],
        {
            "expected_version": 1,
            "expected_session_version": 1,
            "input": {"message": "another turn"},
            "client_message_id": uuid4().hex,
        },
    )
    claimed = claim(engine(client))
    assert claimed
    fresh = ScriptedModel(cache=False, responses=[], outcomes=[message()])
    asyncio.run(execute(engine(client), *claimed, model=fresh))
    assert "SELECTED-SYNTHETIC-ONLY" not in str(fresh.captures)
    assert "已阅读这次资料" not in str(fresh.captures)


@pytest.mark.parametrize("change", ["revision", "delete", "revoke"])
def test_stale_record_cannot_publish(client: TestClient, change: str) -> None:
    row = saved_note(client)
    _, rid, body = create(client)
    g = grant(client, rid, row)
    body["grant_ids"] = [g["id"]]
    start(client, rid, body)
    if change == "revision":
        assert (
            write(
                client, "PATCH", f"/notes/{row['id']}", {"body": "changed", "expected_version": 1}
            ).status_code
            == 200
        )
    elif change == "delete":
        assert (
            write(
                client, "DELETE", f"/notes/{row['id']}", {"expected_version": 1, "confirmed": True}
            ).status_code
            == 202
        )
    else:
        assert (
            write(
                client, "DELETE", f"/context-grants/{g['id']}", {"expected_version": 1}
            ).status_code
            == 200
        )
    assert claim(engine(client)) is None
    assert client.get(f"/api/v1/runs/{rid}").status_code == 404


def test_cross_owner_typed_database_reference_rejected(
    client: TestClient, other: TestClient
) -> None:
    row = saved_note(other)
    _, rid, _ = create(client)
    with Session(engine(client)) as db:
        run = db.get(Run, rid)
        assert run
        db.add(
            ContextGrant(
                owner_id=run.owner_id,
                run_id=rid,
                source_type="note",
                source_id=row["id"],
                source_version=1,
                purpose="current_run",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_cleanup_failure_blocks_then_retries(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = saved_note(client)
    original = deletion.purge_step

    def fail(db: Session, job: Any, step: str) -> None:
        if step == "messages":
            raise RuntimeError("synthetic failure")
        original(db, job, step)

    monkeypatch.setattr(deletion, "purge_step", fail)
    removed = write(
        client, "DELETE", f"/notes/{row['id']}", {"expected_version": 1, "confirmed": True}
    ).json()
    assert removed["status"] == "failed_retryable"
    assert client.get(f"/api/v1/notes/{row['id']}").status_code == 404
    monkeypatch.setattr(deletion, "purge_step", original)
    result = post(
        client,
        f"/deletion-jobs/{removed['deletion_id']}/retry",
        {"expected_version": removed["version"]},
    )
    assert result.json()["status"] == "completed"


def test_partial_updates_preserve_unspecified_fields(client: TestClient) -> None:
    row = saved_note(client, title="preserve", tags=["synthetic"], status="draft")
    changed = write(
        client, "PATCH", f"/notes/{row['id']}", {"expected_version": 1, "title": "new title"}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["body"] == row["body"] and changed.json()["tags"] == ["synthetic"]
    assert changed.json()["status"] == "draft"
    sleep = post(
        client,
        "/sleep-records",
        {
            "entry_date": "2026-09-30",
            "bed_at": "2026-09-30T13:00:00+08:00",
            "timezone": "Asia/Shanghai",
        },
    ).json()
    changed = write(
        client,
        "PATCH",
        f"/sleep-records/{sleep['id']}",
        {"expected_version": 1, "feeling": "rested"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["bed_at"] == sleep["bed_at"] and changed.json()["wake_at"] is None


def test_running_provider_cannot_publish_after_record_changes(client: TestClient) -> None:
    row = saved_note(client)
    _, rid, body = create(client)
    body["grant_ids"] = [grant(client, rid, row)["id"]]
    start(client, rid, body)
    claimed = claim(engine(client))
    assert claimed
    model = ScriptedModel(cache=False, responses=[], outcomes=[message()], delay=1)

    async def race() -> None:
        task = asyncio.create_task(execute(engine(client), *claimed, model=model))
        for _ in range(100):
            if model.calls:
                break
            await asyncio.sleep(0.01)
        assert model.calls == 1
        response = await asyncio.to_thread(
            write,
            client,
            "PATCH",
            f"/notes/{row['id']}",
            {"expected_version": 1, "body": "changed while running"},
        )
        assert response.status_code == 200
        await task

    asyncio.run(race())
    assert client.get(f"/api/v1/runs/{rid}").status_code == 404
    with Session(engine(client)) as db:
        run = db.get(Run, rid)
        assert run is not None and run.status == "cancelled"


def test_source_delete_blocks_excerpt_even_when_cleanup_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sid, rid, body = create(client)
    start(client, rid, body)
    assert execute_one(engine(client))
    turn = current(client, sid)
    note = post(
        client,
        "/notes",
        {
            "kind": "linked_excerpt",
            "source_refs": [
                {
                    "source_type": "message",
                    "source_id": turn["input_id"],
                    "source_version": turn["input_version"],
                }
            ],
        },
    ).json()
    original = deletion.purge_step

    def fail(db: Session, job: Any, step: str) -> None:
        raise RuntimeError("synthetic storage outage")

    monkeypatch.setattr(deletion, "purge_step", fail)
    receipt = remove(client, sid).json()
    assert receipt["status"] == "failed_retryable"
    assert client.get(f"/api/v1/notes/{note['id']}").status_code == 404
    assert client.get("/api/v1/notes").json()["items"] == []
    monkeypatch.setattr(deletion, "purge_step", original)
    result = post(
        client,
        f"/deletion-jobs/{receipt['deletion_id']}/retry",
        {"expected_version": receipt["version"]},
    )
    assert result.json()["status"] == "completed"
