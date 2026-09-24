"""Real PostgreSQL acceptance. Separate command; never silently skip missing storage."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.models import (
    Consent,
    ContextGrant,
    Conversation,
    DeletionJob,
    IdentitySession,
    Preferences,
    Run,
    User,
    now,
)
from app.security import password_hash

ORIGIN = "https://synthetic.local"
pytestmark = pytest.mark.postgres


def test_identity_purpose_versions_and_storage() -> None:
    url = os.environ["PSYEVO_TEST_DATABASE_URL"]

    async def check() -> None:
        app = create_app(
            Settings(environment="test", database_url=SecretStr(url), browser_origin=ORIGIN)
        )
        async with app.router.lifespan_context(app):
            with Session(app.state.engine) as db, db.begin():
                a = User(
                    email="a-" + uuid4().hex + "@example.com",
                    password_hash=password_hash("synthetic-password-a"),
                )
                b = User(
                    email="b-" + uuid4().hex + "@example.com",
                    password_hash=password_hash("synthetic-password-b"),
                )
                db.add_all([a, b])
                db.flush()
                aid, bid, aname, bname = a.id, b.id, a.email, b.email
                db.add_all([Preferences(owner_id=aid), Preferences(owner_id=bid)])
            transport = httpx.ASGITransport(app)
            async with (
                httpx.AsyncClient(transport=transport, base_url=ORIGIN) as ca,
                httpx.AsyncClient(transport=transport, base_url=ORIGIN) as cb,
            ):
                assert (await ca.get("/api/v1/me/preferences")).status_code == 401
                assert (
                    await ca.post(
                        "/api/v1/auth/login",
                        json={"email": aname, "password": "synthetic-password-a"},
                    )
                ).status_code == 403
                for client, username, password in [
                    (ca, aname, "synthetic-password-a"),
                    (cb, bname, "synthetic-password-b"),
                ]:
                    client.headers["Origin"] = ORIGIN
                    login = await client.post(
                        "/api/v1/auth/login", json={"email": username, "password": password}
                    )
                    assert login.status_code == 200, login.text
                    assert all(
                        flag in login.headers["set-cookie"].lower()
                        for flag in ["httponly", "secure", "samesite=strict"]
                    )
                    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
                ca.headers["Idempotency-Key"] = uuid4().hex
                assert (
                    await ca.post("/api/v1/sessions", json={}, headers={"X-CSRF-Token": "wrong"})
                ).status_code == 403
                leak = await ca.post(
                    "/api/v1/sessions", json={"owner_id": bid, "title": "private-marker"}
                )
                assert (
                    leak.status_code == 422
                    and "private-marker" not in leak.text
                    and bid not in leak.text
                )
                assert set(leak.json()) == {"code", "message", "request_id", "retryable"}
                created = await ca.post("/api/v1/sessions", json={})
                assert created.status_code == 201, created.text
                sid = created.json()["id"]
                assert created.headers["cache-control"] == "no-store"
                assert (await ca.post("/api/v1/sessions", json={})).json()["id"] == sid
                assert (
                    await ca.post("/api/v1/sessions", json={"title": "different"})
                ).status_code == 409
                for method, path, data in [
                    ("GET", f"/sessions/{sid}", None),
                    ("PATCH", f"/sessions/{sid}", {"title": "stolen", "expected_version": 1}),
                ]:
                    denied = await cb.request(method, "/api/v1" + path, json=data)
                    assert denied.status_code == 404
                p = (await ca.get("/api/v1/me/preferences")).json()
                assert p["age_band"] == "unknown" and p["age_source"] == "not_provided"
                for age in ["adult", "minor", "unknown"]:
                    updated = await ca.patch(
                        "/api/v1/me/preferences",
                        json={"age_band": age, "expected_version": p["version"]},
                    )
                    assert updated.status_code == 200
                    p = updated.json()
                    assert p["age_band"] == age
                    assert p["age_source"] == (
                        "not_provided" if age == "unknown" else "self_reported"
                    )
                    for purpose in ["optional_profile", "saved_memory", "research"]:
                        ca.headers["Idempotency-Key"] = uuid4().hex
                        denied = await ca.post(
                            "/api/v1/consents",
                            json={
                                "purpose": purpose,
                                "decision": "granted",
                                "notice_version": "synthetic-notice/1",
                            },
                        )
                        assert denied.status_code == 422
                results = await asyncio.gather(
                    *[
                        ca.patch(
                            "/api/v1/me/preferences",
                            json={"age_band": "adult", "expected_version": p["version"]},
                        )
                        for _ in range(2)
                    ]
                )
                assert sorted(r.status_code for r in results) == [200, 409]
                for purpose in ["optional_profile", "saved_memory", "research"]:
                    ca.headers["Idempotency-Key"] = uuid4().hex
                    r = await ca.post(
                        "/api/v1/consents",
                        json={
                            "purpose": purpose,
                            "decision": "declined",
                            "notice_version": "synthetic-notice/1",
                        },
                    )
                    assert r.status_code == 201
                    assert r.json()["effective_scope"] == []
                ca.headers["Idempotency-Key"] = uuid4().hex
                draft_body = {
                    "context_type": "conversation",
                    "session_id": sid,
                    "expected_session_version": 1,
                }
                draft = await ca.post("/api/v1/run-drafts", json=draft_body)
                assert draft.status_code == 201
                rid = draft.json()["id"]
                assert draft.json()["status"] == "draft"
                assert (await ca.post(f"/api/v1/runs/{rid}/start", json={})).status_code == 404
                assert (await cb.get(f"/api/v1/runs/{rid}")).status_code == 404
                ca.headers["Idempotency-Key"] = uuid4().hex
                c = await ca.post(
                    "/api/v1/consents",
                    json={
                        "purpose": "service_context",
                        "decision": "granted",
                        "scope": ["current_run"],
                        "notice_version": "synthetic-notice/1",
                    },
                )
                assert c.status_code == 201
                cid = c.json()["id"]
                ca.headers["Idempotency-Key"] = uuid4().hex
                grant_body = {
                    "run_id": rid,
                    "source_type": "conversation",
                    "source_id": sid,
                    "source_version": 1,
                    "purpose": "current_run",
                }
                g = await ca.post("/api/v1/context-grants", json=grant_body)
                assert g.status_code == 201, g.text
                gid = g.json()["id"]
                assert g.json()["active"]
                assert (await cb.get(f"/api/v1/context-grants/{gid}")).status_code == 404
                assert (
                    await cb.request(
                        "DELETE", f"/api/v1/consents/{cid}", json={"expected_version": 1}
                    )
                ).status_code == 404
                assert (
                    await ca.patch(
                        f"/api/v1/sessions/{sid}", json={"title": "changed", "expected_version": 1}
                    )
                ).status_code == 200
                assert not (await ca.get(f"/api/v1/context-grants/{gid}")).json()["active"]
                assert (await ca.post("/api/v1/context-grants", json=grant_body)).status_code == 403
                ca.headers["Idempotency-Key"] = uuid4().hex
                grant_body["source_version"] = 2
                g2 = await ca.post("/api/v1/context-grants", json=grant_body)
                assert g2.status_code == 201
                gid2 = g2.json()["id"]
                assert (
                    await ca.request(
                        "DELETE", f"/api/v1/consents/{cid}", json={"expected_version": 1}
                    )
                ).status_code == 200
                # Historical consent decisions no longer gate experiment source links.
                assert (await ca.get(f"/api/v1/context-grants/{gid2}")).json()["active"]
                ca.headers["Idempotency-Key"] = uuid4().hex
                assert (await ca.post("/api/v1/context-grants", json=grant_body)).status_code == 201
                assert (await ca.get("/api/v1/auth/session")).status_code == 200
                ca.headers["Idempotency-Key"] = uuid4().hex
                assert (await ca.post("/api/v1/sessions", json={})).status_code == 201
                with Session(app.state.engine) as db, db.begin():
                    source = db.get(Conversation, sid)
                    assert source is not None and source.owner_id == aid
                    source.deleted_at, source.status = now(), "deleted"
                    source.version += 1
                    deletion = DeletionJob(
                        owner_id=aid,
                        target=sid,
                        scope=["conversation"],
                        status="failed_retryable",
                        completed_steps=["online_blocked"],
                        error_code="synthetic_cleanup_failure",
                    )
                    db.add(deletion)
                    db.flush()
                    deletion_id = deletion.id
                    assert db.get(Run, rid) is not None
                    assert db.get(ContextGrant, gid) is not None
                    assert db.get(Consent, cid) is not None
                assert (await ca.get(f"/api/v1/sessions/{sid}")).status_code == 404
                assert (await ca.get(f"/api/v1/runs/{rid}")).status_code == 404
                stale_cookie = ca.cookies.get("psyevo_session")
                assert (await ca.post("/api/v1/auth/logout")).status_code == 204
                ca.cookies.set("psyevo_session", str(stale_cookie))
                assert (await ca.get("/api/v1/auth/session")).status_code == 401
                with Session(app.state.engine) as db, db.begin():
                    auth = db.scalar(select(IdentitySession).where(IdentitySession.owner_id == bid))
                    assert auth is not None
                    auth.expires_at = now() - timedelta(seconds=1)
                assert (await cb.get("/api/v1/auth/session")).status_code == 401

        # New engine/application proves persisted identity, preferences and deletion state.
        restarted = create_app(
            Settings(environment="test", database_url=SecretStr(url), browser_origin=ORIGIN)
        )
        async with restarted.router.lifespan_context(restarted):
            with Session(restarted.state.engine) as db:
                job = db.get(DeletionJob, deletion_id)
                assert job is not None and job.status == "failed_retryable"
                assert job.completed_steps == ["online_blocked"]
                pref = db.scalar(select(Preferences).where(Preferences.owner_id == aid))
                assert pref is not None and pref.age_band == "adult"
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(restarted),
                base_url=ORIGIN,
                headers={"Origin": ORIGIN},
            ) as client:
                login = await client.post(
                    "/api/v1/auth/login",
                    json={"email": aname, "password": "synthetic-password-a"},
                )
                assert login.status_code == 200
                assert (await client.get(f"/api/v1/sessions/{sid}")).status_code == 404
                assert (await client.get(f"/api/v1/runs/{rid}")).status_code == 404

    asyncio.run(check())


@pytest.mark.parametrize(
    "change",
    [
        "expired_grant",
        "expired_consent",
        "expired_run",
        "terminal_run",
        "deleted_source",
        "revoked_grant",
    ],
)
def test_grant_rechecks_current_facts(change: str) -> None:
    from app.api import grant_valid
    from app.database import make_engine

    engine = make_engine(os.environ["PSYEVO_TEST_DATABASE_URL"])
    try:
        with Session(engine) as db, db.begin():
            user = User(username=uuid4().hex, password_hash="synthetic-no-login")
            db.add(user)
            db.flush()
            source = Conversation(owner_id=user.id)
            consent = Consent(
                owner_id=user.id,
                purpose="service_context",
                decision="granted",
                scope=["current_run"],
                notice_version="synthetic-notice/1",
            )
            db.add_all([source, consent])
            db.flush()
            run = Run(
                owner_id=user.id,
                session_id=source.id,
                session_version=1,
            )
            db.add(run)
            db.flush()
            grant = ContextGrant(
                owner_id=user.id,
                purpose="current_run",
                source_id=source.id,
                source_version=1,
                run_id=run.id,
                consent_id=consent.id,
            )
            db.add(grant)
            db.flush()
            assert (
                consent.expires_at is None and run.expires_at is None and grant.expires_at is None
            )
            assert grant_valid(db, grant)
            if change == "expired_grant":
                grant.expires_at = now() - timedelta(seconds=1)
            elif change == "expired_consent":
                consent.expires_at = now() - timedelta(seconds=1)
            elif change == "expired_run":
                run.expires_at = now() - timedelta(seconds=1)
            elif change == "terminal_run":
                run.status = "cancelled"
            elif change == "deleted_source":
                source.deleted_at = now()
            else:
                grant.revoked_at = now()
            db.flush()
            assert grant_valid(db, grant) == change.startswith("expired_")
    finally:
        engine.dispose()
