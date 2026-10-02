"""Automatic titles on an isolated PostgreSQL database and controlled models."""

import asyncio
import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import titles
from app.models import Conversation, Message, ModelCall, Run, TitleTask, now
from app.provider import LiveProfile, open_provider
from app.run_worker import execute_one
from app.runs import execution
from tests import test_runs
from tests.test_history import remove
from tests.test_live_runs import live_settings
from tests.test_provider import response
from tests.test_runs import create, engine, start
from tests.test_support import ScriptedModel

pytestmark = pytest.mark.postgres
client = test_runs.client


def model(title: str = "工作压力与睡眠困扰", delay: float = 0) -> ScriptedModel:
    return ScriptedModel(
        cache=False,
        responses=[],
        delay=delay,
        outcomes=[
            AIMessage(
                content=json.dumps({"title": title}, ensure_ascii=False),
                usage_metadata={"input_tokens": 30, "output_tokens": 10, "total_tokens": 40},
            )
        ],
    )


def ready(client: TestClient) -> tuple[str, str, str]:
    sid, rid, body = create(client)
    start(client, rid, body)
    assert execute_one(engine(client))
    with Session(engine(client)) as db, db.begin():
        source = db.get(Conversation, sid)
        task = db.get(TitleTask, sid)
        assert source is not None and task is not None
        assert source.title_generation_status == "queued"
        source.title_generation_status = "running"
        task.deadline_at = now() + timedelta(seconds=20)
        return sid, rid, source.owner_id


def session(client: TestClient, sid: str) -> dict[str, Any]:
    return dict(client.get(f"/api/v1/sessions/{sid}").json())


def test_legacy_binding_does_not_fail_next_reply(client: TestClient) -> None:
    sid, rid, _ = ready(client)
    with Session(engine(client)) as db, db.begin():
        run = db.get(Run, rid)
        source = db.get(Conversation, sid)
        task = db.get(TitleTask, sid)
        assert run is not None and source is not None and task is not None
        ex = execution(db, run)
        assert ex is not None
        legacy = {k: v for k, v in ex.versions.items() if k != "provider_ref"}
        ex.versions = legacy
        db.delete(task)
        source.title_generation_status = "not_requested"
    result = client.post(
        f"/api/v1/sessions/{sid}/runs",
        headers={"Idempotency-Key": uuid4().hex},
        json={
            "expected_session_version": 1,
            "client_message_id": uuid4().hex,
            "input": {"message": "Synthetic follow-up"},
        },
    )
    assert result.status_code == 202, result.text
    assert execute_one(engine(client))
    with Session(engine(client)) as db:
        followup = db.get(Run, result.json()["run_id"])
        assert followup is not None and followup.status == "completed"
        assert (
            db.scalar(
                select(Message).where(Message.run_id == followup.id, Message.role == "assistant")
            )
            is not None
        )
        task = db.get(TitleTask, sid)
        assert task is not None and task.run_id == rid
        assert task.profile == {"model_ref": "local-scripted/1", "provider_ref": "local-fake"}
        run = db.get(Run, rid)
        assert run is not None
        ex = execution(db, run)
        assert ex is not None and ex.versions == legacy


def test_title_persists_searches_and_does_not_invalidate_active_run(client: TestClient) -> None:
    sid, rid, owner = ready(client)
    # A second reply is already queued when the first title commits.
    result = client.post(
        f"/api/v1/sessions/{sid}/runs",
        headers={"Idempotency-Key": uuid4().hex},
        json={
            "expected_session_version": 1,
            "client_message_id": uuid4().hex,
            "input": {"message": "另一个合成输入"},
        },
    )
    assert result.status_code == 202, result.text
    fake = model()
    asyncio.run(titles.execute(engine(client), sid, owner, fake))
    current = session(client, sid)
    assert (
        current["title"],
        current["title_source"],
        current["title_revision"],
        current["version"],
    ) == (
        "工作压力与睡眠困扰",
        "auto",
        2,
        1,
    )
    assert current["title_generation_status"] == "succeeded"
    assert execute_one(engine(client))
    assert client.get(f"/api/v1/runs/{result.json()['run_id']}").json()["status"] == "completed"
    assert client.get(f"/api/v1/runs/{rid}").json()["budget_used"]["calls"] == 1
    matches = client.get("/api/v1/sessions?q=工作压力").json()["items"]
    assert any(item["id"] == sid for item in matches)
    asyncio.run(titles.execute(engine(client), sid, owner, fake))
    assert fake.calls == 1
    with Session(engine(client)) as db:
        task = db.get(TitleTask, sid)
        assert task is not None and task.run_id == rid
        calls = list(db.scalars(select(ModelCall).where(ModelCall.run_id == rid)))
        assert len(calls) == 2
        title_call = next(c.receipt for c in calls if c.receipt["role"] == "title")
        assert title_call["actual_tokens"] == 40 and title_call["status"] == "settled"
        assert "工作压力" not in str(title_call)


@pytest.mark.parametrize("action", ["rename", "delete", "source_changed"])
def test_late_title_never_overwrites_manual_or_deleted_source(
    client: TestClient, action: str
) -> None:
    sid, _, owner = ready(client)
    fake = model(delay=0.3)

    async def race() -> None:
        pending = asyncio.create_task(titles.execute(engine(client), sid, owner, fake))
        for _ in range(100):
            if fake.calls:
                break
            await asyncio.wait({pending}, timeout=0.01)
        assert fake.calls == 1
        # A duplicate delivery while the original call runs must not invoke again.
        await titles.execute(engine(client), sid, owner, fake)
        assert fake.calls == 1
        if action == "rename":
            result = client.patch(
                f"/api/v1/sessions/{sid}",
                json={
                    "expected_version": 1,
                    "expected_title_revision": 1,
                    "title": "新的对话",
                },
            )
            assert result.status_code == 200
        elif action == "delete":
            assert remove(client, sid).status_code == 202
        else:
            with Session(engine(client)) as db, db.begin():
                task = db.get(TitleTask, sid)
                assert task is not None
                message = db.get(Message, next(iter(task.message_versions)))
                assert message is not None
                message.version += 1
        await pending

    asyncio.run(race())
    with Session(engine(client)) as db:
        source = db.get(Conversation, sid)
        assert source is not None and source.title_generation_status == "cancelled"
        assert source.title_source != "auto"
        if action == "delete":
            assert db.get(TitleTask, sid) is None and source.title == "已删除的对话"
        elif action == "rename":
            assert source.title_source == "manual" and source.title == "新的对话"


@pytest.mark.parametrize(
    "failure", ["invalid", "missing_usage", "provider_error", "deadline", "deadline_before_call"]
)
def test_failure_keeps_default_and_never_retries(client: TestClient, failure: str) -> None:
    sid, _, owner = ready(client)
    fake = model("x" * 25 if failure == "invalid" else "工作压力")
    if failure == "missing_usage":
        fake.outcomes = [AIMessage(content='{"title":"工作压力"}')]
    elif failure == "provider_error":
        fake.outcomes = [RuntimeError("synthetic failure")]
    elif failure in {"deadline", "deadline_before_call"}:
        fake.delay = 0.5
        with Session(engine(client)) as db, db.begin():
            task = db.get(TitleTask, sid)
            assert task is not None
            task.deadline_at = now() + timedelta(seconds=0.1 if failure == "deadline" else -1)
    asyncio.run(titles.execute(engine(client), sid, owner, fake))
    assert session(client, sid)["title"] == "新的对话"
    assert session(client, sid)["title_generation_status"] in {"failed", "cancelled"}
    asyncio.run(titles.execute(engine(client), sid, owner, fake))
    if failure == "deadline_before_call":
        assert fake.calls == 0
    elif failure == "deadline":
        # Load can consume the remaining 100ms before dispatch; neither path may retry.
        assert fake.calls in {0, 1}
    else:
        assert fake.calls == 1


def test_manual_creation_and_stale_title_revision(client: TestClient) -> None:
    explicit = client.post(
        "/api/v1/sessions", json={"title": "新的对话"}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert explicit.json()["title_source"] == "manual"
    sid, _, owner = ready(client)
    asyncio.run(titles.execute(engine(client), sid, owner, model()))
    stale = client.patch(
        f"/api/v1/sessions/{sid}",
        json={
            "expected_version": 1,
            "expected_title_revision": 1,
            "title": "手动主题",
        },
    )
    assert stale.status_code == 409
    legacy = client.patch(
        f"/api/v1/sessions/{sid}", json={"expected_version": 1, "title": "手动主题"}
    )
    assert legacy.status_code == 200 and legacy.json()["title_source"] == "manual"


def test_expired_claim_is_not_reissued(client: TestClient) -> None:
    sid, _, _ = ready(client)
    with Session(engine(client)) as db, db.begin():
        task = db.get(TitleTask, sid)
        assert task is not None
        task.deadline_at = now() - timedelta(seconds=1)
    # Other synthetic tests may have left queued jobs; consume them normally.
    while titles.execute_one(engine(client)):
        pass
    assert session(client, sid)["title_generation_status"] == "failed"


def test_old_default_session_uses_earliest_valid_turn(client: TestClient) -> None:
    sid, rid, _ = ready(client)
    with Session(engine(client)) as db, db.begin():
        task, source = db.get(TitleTask, sid), db.get(Conversation, sid)
        assert task is not None and source is not None
        db.delete(task)
        source.title_generation_status = "not_requested"
    result = client.post(
        f"/api/v1/sessions/{sid}/runs",
        headers={"Idempotency-Key": uuid4().hex},
        json={
            "expected_session_version": 1,
            "client_message_id": uuid4().hex,
            "input": {"message": "后续合成输入"},
        },
    )
    assert result.status_code == 202
    assert execute_one(engine(client))
    with Session(engine(client)) as db:
        task = db.get(TitleTask, sid)
        assert task is not None and task.run_id == rid
        assert db.get(Run, rid) is not None


def test_title_uses_actual_sdk_and_retains_external_receipt(client: TestClient) -> None:
    from app.run_worker import claim, execute

    config = live_settings(client).model_copy(update={"provider_max_output_tokens": 256})
    sid, rid, body = create(client)
    start(client, rid, body)
    selected = claim(engine(client))
    assert selected is not None and selected[0] == rid
    owner = selected[1]
    calls = 0

    async def transport(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        payload = json.loads(req.content)
        assert payload["max_tokens"] == 256
        text = '{"text":"我先听你说。"}' if calls == 1 else '{"title":"工作压力与睡眠困扰"}'
        return httpx.Response(
            200, content=response(text), headers={"content-type": "text/event-stream"}
        )

    async def run() -> None:
        async with open_provider(config, transport=httpx.MockTransport(transport)) as provider:
            await execute(
                engine(client),
                rid,
                owner,
                provider,
                LiveProfile(
                    model_ref=config.provider_model,
                    base_url=config.provider_base_url,
                ),
            )
            with Session(engine(client)) as db, db.begin():
                source = db.get(Conversation, sid)
                assert source is not None and source.title_generation_status == "queued"
                source.title_generation_status = "running"
            await titles.execute(engine(client), sid, owner, provider, config)

    asyncio.run(run())
    assert calls == 2 and session(client, sid)["title_source"] == "auto"
    with Session(engine(client)) as db:
        receipt = db.scalar(
            select(ModelCall).where(
                ModelCall.run_id == rid,
                ModelCall.receipt["role"].astext == "title",
            )
        )
        assert receipt is not None
        assert receipt.receipt["actual_tokens"] == 30
        assert receipt.receipt["actual_cost"] is None
        assert receipt.receipt["currency"] == "unknown"
    assert remove(client, sid).json()["external_provider_status"] == "unknown"
