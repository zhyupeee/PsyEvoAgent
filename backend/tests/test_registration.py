"""Registration and default configuration using a real, isolated PostgreSQL database."""

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Consent, Preferences, User
from app.security import password_hash
from tests.mail_support import MemoryMailer, mail_settings


@pytest.mark.postgres
def test_register_login_defaults_and_legacy_account() -> None:
    async def check() -> None:
        origin = "https://experiment.example"
        mail = MemoryMailer()
        app = create_app(
            mail_settings(
                database_url=SecretStr(os.environ["PSYEVO_TEST_DATABASE_URL"]),
                browser_origin=origin,
            ),
            mail,
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url=origin, headers={"Origin": origin}
            ) as client:
                email = "register-" + uuid4().hex + "@example.com"
                assert (
                    await client.post("/api/v1/auth/registration-codes", json={"email": email})
                ).status_code == 202
                body = {"email": email, "password": "12345678", "code": mail.code(email)}
                for bad_origin in ("https://other.example", origin + ".evil", "null"):
                    assert (
                        await client.post(
                            "/api/v1/auth/register", json=body, headers={"Origin": bad_origin}
                        )
                    ).status_code == 403
                assert (
                    await client.post("/api/v1/auth/register", json={**body, "password": "12345"})
                ).status_code == 422
                registered = await client.post("/api/v1/auth/register", json=body)
                assert registered.status_code == 201
                uid = registered.json()["user_id"]
                client.headers["X-CSRF-Token"] = registered.json()["csrf_token"]
                assert (await client.get("/api/v1/auth/session")).json()["user_id"] == uid
                assert (await client.post("/api/v1/auth/register", json=body)).status_code == 400
                pref = (await client.get("/api/v1/me/preferences")).json()
                assert pref["age_band"] == "unknown" and pref["age_source"] == "not_provided"
                config = (await client.get("/api/v1/experiment-config")).json()
                assert config["version"] == "experiment-defaults/1"
                assert all(config["defaults"].values()) and config["user_consent"] is False
                with Session(app.state.engine) as db:
                    assert (
                        db.scalar(
                            select(func.count()).select_from(Consent).where(Consent.owner_id == uid)
                        )
                        == 0
                    )

                def key() -> dict[str, str]:
                    return {"Idempotency-Key": uuid4().hex}

                source = (await client.post("/api/v1/sessions", json={}, headers=key())).json()
                run = (
                    await client.post(
                        "/api/v1/run-drafts",
                        json={
                            "context_type": "conversation",
                            "session_id": source["id"],
                            "expected_session_version": 1,
                        },
                        headers=key(),
                    )
                ).json()
                grant_body = {
                    "run_id": run["id"],
                    "source_id": source["id"],
                    "source_type": "conversation",
                    "source_version": 1,
                    "purpose": "current_run",
                }
                grant = await client.post("/api/v1/context-grants", json=grant_body, headers=key())
                assert grant.status_code == 201 and grant.json()["active"]
                assert grant.json()["consent_id"] is None and grant.json()["consent_refs"] == []
                assert grant.json()["expires_at"] is None
                assert (
                    await client.post(
                        "/api/v1/context-grants",
                        json={**grant_body, "consent_id": "invented"},
                        headers=key(),
                    )
                ).status_code == 422
                assert (
                    await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "bad"})
                ).status_code == 403
                assert (await client.post("/api/v1/auth/logout")).status_code == 204
                assert (await client.get("/api/v1/auth/session")).status_code == 401
                assert (
                    await client.post(
                        "/api/v1/auth/login", json={"email": email, "password": "wrong"}
                    )
                ).status_code == 401
                assert (
                    await client.post(
                        "/api/v1/auth/login", json={"email": email, "password": "12345678"}
                    )
                ).status_code == 200
                previous_cookie = client.cookies.get("psyevo_session")
                with Session(app.state.engine) as db, db.begin():
                    old = User(
                        email="other-" + uuid4().hex + "@example.com",
                        password_hash=password_hash("12345678"),
                    )
                    db.add(old)
                    db.flush()
                    old_id, old_name = old.id, old.email
                    db.add(
                        Preferences(owner_id=old_id, age_band="minor", age_source="self_reported")
                    )
                assert (
                    await client.post(
                        "/api/v1/auth/login", json={"email": old_name, "password": "12345678"}
                    )
                ).status_code == 200
                assert (
                    await client.get(f"/api/v1/context-grants/{grant.json()['id']}")
                ).status_code == 404
                assert (await client.get("/api/v1/me/preferences")).json()["age_band"] == "minor"
                client.cookies.clear()
                client.cookies.set("psyevo_session", str(previous_cookie))
                assert (await client.get("/api/v1/auth/session")).status_code == 401

    asyncio.run(check())
