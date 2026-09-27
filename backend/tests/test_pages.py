"""STEP06 current-turn recovery and static content boundary on isolated PostgreSQL."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, IdentitySession, ModelCall, Run, User, now
from app.run_worker import execute_one
from tests import test_runs
from tests.test_runs import create, engine, start

client = test_runs.client

pytestmark = pytest.mark.postgres


def test_current_turn_recovery_and_revoked_source(client: TestClient) -> None:
    sid, rid, body = create(client, grant=True)
    assert client.get(f"/api/v1/sessions/{sid}/current-run").json()["status"] == "draft"
    start(client, rid, body)
    assert execute_one(engine(client))
    response = client.get(f"/api/v1/sessions/{sid}/current-run")
    assert response.status_code == 200
    assert response.json()["input_text"] == body["input"]["message"]
    assert response.json()["output"]["text"]
    client.request(
        "DELETE", "/api/v1/context-grants/" + body["grant_ids"][0], json={"expected_version": 1}
    )
    hidden = client.get(f"/api/v1/sessions/{sid}/current-run")
    assert hidden.status_code == 404
    assert body["input"]["message"] not in hidden.text


def test_current_turn_owner_and_deleted_session(client: TestClient) -> None:
    sid, _, _ = create(client)
    with Session(engine(client)) as db, db.begin():
        conversation = db.get(Conversation, sid)
        assert conversation is not None
        conversation.deleted_at = now()
    assert client.get(f"/api/v1/sessions/{sid}/current-run").status_code == 404
    sid, _, _ = create(client)
    with Session(engine(client)) as db, db.begin():
        conversation = db.get(Conversation, sid)
        assert conversation is not None
        identity = db.scalar(
            select(IdentitySession).where(IdentitySession.owner_id == conversation.owner_id)
        )
        assert identity is not None
        other = User(email="pages-other-" + sid + "@example.com", password_hash="unused")
        db.add(other)
        db.flush()
        identity.owner_id = other.id
    assert client.get(f"/api/v1/sessions/{sid}/current-run").status_code == 404


def test_current_turn_excludes_deleted_run(client: TestClient) -> None:
    sid, rid, body = create(client)
    start(client, rid, body)
    assert execute_one(engine(client))
    current = client.get(f"/api/v1/sessions/{sid}/current-run")
    assert current.status_code == 200
    assert current.json()["input_text"] == body["input"]["message"]
    assert current.json()["output"]["text"]

    with Session(engine(client)) as db, db.begin():
        run = db.get(Run, rid)
        assert run is not None
        run.deleted_at = now()

    assert client.get(f"/api/v1/runs/{rid}").status_code == 404
    hidden = client.get(f"/api/v1/sessions/{sid}/current-run")
    assert hidden.status_code == 200
    assert hidden.json() is None


def test_exercise_independent_of_model_and_unreviewed_content_gate(client: TestClient) -> None:
    assert isinstance(client.app, FastAPI)
    original = client.app.state.settings
    client.app.state.settings = original.model_copy(update={"support_mode": "disabled"})
    with Session(engine(client)) as db:
        before = list(db.scalars(select(ModelCall.run_id)))
    result = client.get("/api/v1/resources/exercises/attention")
    assert result.status_code == 200
    assert result.json()["available"] and len(result.json()["steps"]) == 3
    assert result.json()["review_status"] == "unreviewed"
    client.app.state.settings = original.model_copy(
        update={"environment": "development", "support_mode": "disabled"}
    )
    result = client.get("/api/v1/resources/exercises/attention")
    assert not result.json()["available"] and result.json()["steps"] == []
    assert client.get("/api/v1/resources/support").json()["items"] == []
    with Session(engine(client)) as db:
        assert list(db.scalars(select(ModelCall.run_id))) == before
    client.app.state.settings = original
