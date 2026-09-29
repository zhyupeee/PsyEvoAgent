"""Controlled SDK and isolated PostgreSQL checks for stage-1 conversation context."""

import asyncio
import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.history import context_available, context_history
from app.models import ContextGrant, IdentitySession, Message, Run, User, now
from app.provider import LiveProfile, open_provider
from app.run_worker import claim, execute, execute_one
from app.security import digest
from app.support import (
    Budget,
    ContextTurn,
    SupportRuntime,
    VersionBinding,
    context_size,
    fit_history,
    history_capacity,
    select_mode,
)
from tests import test_runs
from tests.test_history import post, remove
from tests.test_live_runs import live_settings
from tests.test_provider import request, response, settings
from tests.test_runs import create, engine, start

client = test_runs.client


def prior(text: str) -> ContextTurn:
    return ContextTurn(
        run_id=str(uuid4()),
        user_id=str(uuid4()),
        user_version=1,
        assistant_id=str(uuid4()),
        assistant_version=1,
        user_text=text,
        assistant_text="前一轮已发布回答",
    )


def test_budget_keeps_current_and_newest_whole_turns() -> None:
    original = request()
    turns = (prior("旧" * 1500), prior("新" * 1500))
    bound = Budget(max_tokens=8192)
    capacity = history_capacity(original.source.content, select_mode(original), bound)
    assert context_size(turns[0]) < capacity < sum(map(context_size, turns))
    assert fit_history(original.model_copy(update={"history": turns}), bound) == turns[1:]
    assert Budget().max_tokens == 8192
    legacy = original.model_copy(
        update={"history": turns, "versions": VersionBinding(policy_version="support-policy/1")}
    )
    assert fit_history(legacy, bound) == ()


@pytest.mark.parametrize("over_budget", [False, True])
def test_real_sdk_serializes_roles_and_trims_before_call(over_budget: bool) -> None:
    payloads: list[dict[str, Any]] = []
    config = settings()

    async def check() -> None:
        async def handle(req: httpx.Request) -> httpx.Response:
            payloads.append(json.loads(req.content))
            return httpx.Response(
                200, content=response(), headers={"content-type": "text/event-stream"}
            )

        async with open_provider(config, transport=httpx.MockTransport(handle)) as adapter:
            runtime = SupportRuntime(
                adapter,
                profile=LiveProfile(
                    model_ref=config.provider_model, base_url=config.provider_base_url
                ),
                authorize=lambda _: True,
            )
            data = request().model_copy(
                update={"history": (prior("旧" * 12000), prior("最近输入"))}
            )
            result = await runtime.run(
                data, Budget(max_calls=1, max_tokens=100 if over_budget else 32768)
            )
            if over_budget:
                assert (
                    result.stop_reason == "token_budget"
                    and not payloads
                    and not result.ledger.calls
                )
            else:
                assert result.text and result.ledger.calls[0].reserved_tokens == 32768
                messages = payloads[0]["messages"]
                assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
                assert [m["content"] for m in messages[1:]] == [
                    "最近输入",
                    "前一轮已发布回答",
                    data.source.content,
                ]
                assert payloads[0]["max_tokens"] == config.provider_max_output_tokens

    asyncio.run(check())


def send(client: TestClient, sid: str, text: str) -> str:
    result = post(
        client,
        f"/sessions/{sid}/runs",
        {
            "expected_session_version": 1,
            "client_message_id": uuid4().hex,
            "input": {"message": text},
        },
    )
    assert result.status_code == 202, result.text
    return str(result.json()["run_id"])


@pytest.mark.postgres
def test_timeline_pagination_revision_and_scope(client: TestClient) -> None:
    sid, rid, body = create(client)
    start(client, rid, body)
    assert execute_one(engine(client))
    second = send(client, sid, "第二轮")
    assert execute_one(engine(client))
    newest = client.get(f"/api/v1/sessions/{sid}/timeline?limit=1").json()
    assert [t["run_id"] for t in newest["items"]] == [second]
    old = client.get(
        f"/api/v1/sessions/{sid}/timeline?cursor={newest['next_cursor']}&limit=1"
    ).json()
    assert [t["run_id"] for t in old["items"]] == [rid] and old["next_cursor"] is None
    current = newest["items"][0]
    versions_url = f"/api/v1/sessions/{sid}/history?old_only=true&limit=1"
    assert client.get(versions_url).json() == {"items": [], "next_cursor": None}
    draft = post(
        client,
        f"/sessions/{sid}/messages/{current['input_id']}/revisions",
        {"expected_version": current["input_version"], "content": "替代输入"},
    ).json()
    timeline = client.get(f"/api/v1/sessions/{sid}/timeline").json()["items"]
    assert [t["run_id"] for t in timeline] == [rid, draft["run_id"]]
    assert timeline[-1]["status"] == "draft"
    versions = client.get(versions_url).json()
    assert [item["run_id"] for item in versions["items"]] == [second]
    assert versions["next_cursor"] is None
    with Session(engine(client)) as db:
        revised = db.get(Run, draft["run_id"])
        assert revised
        assert [t.run_id for t in context_history(db, revised, request(), Budget())] == [rid]
    other, other_run, _ = create(client)
    assert client.get(f"/api/v1/sessions/{sid}/timeline?cursor={other_run}").status_code == 422
    assert client.get(f"/api/v1/sessions/{other}/timeline").json()["items"] == []
    cookie = client.cookies.get("psyevo_session")
    other_token = uuid4().hex
    with Session(engine(client)) as db, db.begin():
        stranger = User(email=uuid4().hex + "@example.com", password_hash="synthetic-unused")
        db.add(stranger)
        db.flush()
        db.add(
            IdentitySession(
                owner_id=stranger.id,
                token_hash=digest(other_token),
                csrf_token="test-csrf",
                expires_at=now() + timedelta(hours=1),
            )
        )
    client.cookies.set("psyevo_session", other_token)
    denied = client.get(f"/api/v1/sessions/{sid}/timeline")
    assert client.get(versions_url).status_code == 404
    assert denied.status_code == 404 and body["input"]["message"] not in denied.text
    client.cookies.set("psyevo_session", "invalid")
    assert client.get(f"/api/v1/sessions/{sid}/timeline").status_code == 401
    assert cookie is not None
    client.cookies.set("psyevo_session", cookie)
    assert remove(client, sid).status_code == 202
    assert client.get(f"/api/v1/sessions/{sid}/timeline").status_code == 404


@pytest.mark.postgres
@pytest.mark.parametrize("invalidate", [None, "revoked", "deleted", "version"])
def test_worker_context_and_source_invalidation(client: TestClient, invalidate: str | None) -> None:
    sid, rid, body = create(client, grant=True)
    start(client, rid, body)
    assert execute_one(engine(client))
    config = live_settings(client)
    second = send(client, sid, "请参考上一轮")
    selected = claim(engine(client))
    assert selected and selected[0] == second
    captures: list[dict[str, Any]] = []

    async def check() -> None:
        async def handle(req: httpx.Request) -> httpx.Response:
            captures.append(json.loads(req.content))
            if invalidate:
                with Session(engine(client)) as db, db.begin():
                    if invalidate == "revoked":
                        grant = db.get(ContextGrant, body["grant_ids"][0])
                        assert grant
                        grant.revoked_at = now()
                    else:
                        message = db.scalar(
                            select(Message).where(
                                Message.run_id == rid, Message.role == "assistant"
                            )
                        )
                        assert message
                        if invalidate == "deleted":
                            message.deleted_at = now()
                        else:
                            message.version += 1
            return httpx.Response(
                200, content=response(), headers={"content-type": "text/event-stream"}
            )

        async with open_provider(config, transport=httpx.MockTransport(handle)) as adapter:
            await execute(
                engine(client),
                second,
                selected[1],
                adapter,
                LiveProfile(model_ref=config.provider_model, base_url=config.provider_base_url),
            )

    asyncio.run(check())
    assert [m["role"] for m in captures[0]["messages"]] == ["system", "user", "assistant", "user"]
    assert captures[0]["messages"][1]["content"] == body["input"]["message"]
    snapshot = client.get(f"/api/v1/runs/{second}").json()
    assert snapshot["status"] == ("cancelled" if invalidate else "completed")
    assert snapshot["budget"]["max_tokens"] == 32768
    if invalidate:
        assert snapshot["output"] is None


@pytest.mark.postgres
def test_history_selection_excludes_cancelled_deleted_and_revoked(client: TestClient) -> None:
    sid, rid, body = create(client, grant=True)
    start(client, rid, body)
    assert execute_one(engine(client))
    cancelled = send(client, sid, "取消的输入")
    snap = client.get(f"/api/v1/runs/{cancelled}").json()
    assert (
        client.post(
            f"/api/v1/runs/{cancelled}/cancel", json={"expected_version": snap["version"]}
        ).status_code
        == 200
    )
    newest = send(client, sid, "当前消息")
    with Session(engine(client)) as db, db.begin():
        run = db.get(Run, newest)
        assert run
        data = request()
        history = context_history(db, run, data, Budget())
        assert [t.run_id for t in history] == [rid]
        assert context_available(db, run, history)
        grant = db.get(ContextGrant, body["grant_ids"][0])
        assert grant
        grant.revoked_at = now()
        db.flush()
        assert not context_available(db, run, history)
        assert context_history(db, run, data, Budget()) == ()
    timeline = client.get(f"/api/v1/sessions/{sid}/timeline").json()["items"]
    assert [t["run_id"] for t in timeline] == [cancelled, newest]
