"""Email lifecycle acceptance against disposable PostgreSQL and in-memory mail."""

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.email_identity import consume_code, reserve_code
from app.main import create_app
from app.models import EmailCode, IdentitySession, Preferences, User, now
from app.security import password_hash
from tests.mail_support import MemoryMailer, mail_settings

pytestmark = pytest.mark.postgres
ORIGIN = "https://email.example"


def test_email_lifecycle() -> None:
    async def check() -> None:
        mail = MemoryMailer()
        settings = mail_settings(
            database_url=SecretStr(os.environ["PSYEVO_TEST_DATABASE_URL"]), browser_origin=ORIGIN
        )
        app = create_app(settings, mail)
        async with app.router.lifespan_context(app):
            engine = app.state.engine
            with Session(engine) as db, db.begin():
                db.execute(delete(EmailCode))
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url=ORIGIN, headers={"Origin": ORIGIN}
            ) as c:
                email = uuid4().hex + "@example.com"
                code_path = "/api/v1/auth/registration-codes"
                assert (
                    await c.post(code_path, json={"email": email}, headers={"Origin": "null"})
                ).status_code == 403
                assert (await c.post(code_path, json={"email": "invalid"})).status_code == 422
                mail.fail = True
                assert (await c.post(code_path, json={"email": email})).status_code == 503
                with Session(engine) as db:
                    assert (
                        db.scalar(
                            select(func.count())
                            .select_from(EmailCode)
                            .where(EmailCode.email == email)
                        )
                        == 0
                    )
                mail.fail = False
                sent = await c.post(code_path, json={"email": "  " + email.upper() + "  "})
                assert sent.status_code == 202
                code = mail.code(email)
                with Session(engine) as db:
                    assert db.scalar(select(User).where(User.email == email)) is None
                    row = db.scalar(select(EmailCode).where(EmailCode.email == email))
                    assert row and code not in row.code_hash and row.attempts == 0
                assert (await c.post(code_path, json={"email": email})).status_code == 429
                body = {"email": email, "code": code, "password": "12345678"}
                bad_code = "000000" if code != "000000" else "111111"
                assert (
                    await c.post("/api/v1/auth/register", json={**body, "code": bad_code})
                ).status_code == 400
                with Session(engine) as db:
                    attempt = db.scalar(select(EmailCode).where(EmailCode.email == email))
                    assert attempt is not None and attempt.attempts == 1
                registered = await c.post("/api/v1/auth/register", json=body)
                assert registered.status_code == 201, registered.text
                assert registered.json()["email"] == email
                uid = registered.json()["user_id"]
                csrf = registered.json()["csrf_token"]
                first_cookie = c.cookies.get("psyevo_session")
                assert (await c.post("/api/v1/auth/register", json=body)).status_code == 400
                with Session(engine) as db:
                    pref = db.scalar(select(Preferences).where(Preferences.owner_id == uid))
                    assert pref and pref.age_band == "unknown"
                c.cookies.clear()
                second = await c.post(
                    "/api/v1/auth/login", json={"email": email, "password": "12345678"}
                )
                assert second.status_code == 200
                second_cookie = c.cookies.get("psyevo_session")
                csrf = second.json()["csrf_token"]
                change = {"current_password": "12345678", "new_password": "next-password"}
                assert (
                    await c.post("/api/v1/auth/password-change", json=change)
                ).status_code == 403
                assert (
                    await c.post(
                        "/api/v1/auth/password-change",
                        json=change,
                        headers={"Origin": "null", "X-CSRF-Token": csrf},
                    )
                ).status_code == 403
                assert (
                    await c.post(
                        "/api/v1/auth/password-change",
                        json={**change, "current_password": "bad"},
                        headers={"X-CSRF-Token": csrf},
                    )
                ).status_code == 400
                assert (
                    await c.post(
                        "/api/v1/auth/password-change", json=change, headers={"X-CSRF-Token": csrf}
                    )
                ).status_code == 204
                for cookie in (first_cookie, second_cookie):
                    c.cookies.clear()
                    c.cookies.set(
                        "psyevo_session", str(cookie), domain="email.example", path="/api/v1"
                    )
                    assert (await c.get("/api/v1/auth/session")).status_code == 401
                assert (
                    await c.post(
                        "/api/v1/auth/login", json={"email": email, "password": "12345678"}
                    )
                ).status_code == 401
                assert (
                    await c.post(
                        "/api/v1/auth/login", json={"email": email, "password": "next-password"}
                    )
                ).status_code == 200
                cookie_before_reset = c.cookies.get("psyevo_session")
                with Session(engine) as db, db.begin():
                    db.execute(
                        update(EmailCode)
                        .where(EmailCode.email == email)
                        .values(created_at=now() - timedelta(minutes=2))
                    )
                assert (
                    await c.post("/api/v1/auth/password-reset-codes", json={"email": email})
                ).status_code == 202
                reset_code = mail.code(email)
                reset = {"email": email, "code": reset_code, "new_password": "reset-password"}
                assert (
                    await c.post("/api/v1/auth/register", json={**body, "code": reset_code})
                ).status_code == 400
                assert (
                    await c.post("/api/v1/auth/password-reset", json={**reset, "code": bad_code})
                ).status_code == 400
                assert (await c.post("/api/v1/auth/password-reset", json=reset)).status_code == 204
                assert (await c.post("/api/v1/auth/password-reset", json=reset)).status_code == 400
                c.cookies.clear()
                c.cookies.set(
                    "psyevo_session",
                    str(cookie_before_reset),
                    domain="email.example",
                    path="/api/v1",
                )
                assert (await c.get("/api/v1/auth/session")).status_code == 401
                assert (
                    await c.post(
                        "/api/v1/auth/login", json={"email": email, "password": "next-password"}
                    )
                ).status_code == 401
                assert (
                    await c.post(
                        "/api/v1/auth/login", json={"email": email, "password": "reset-password"}
                    )
                ).status_code == 200
                unknown = uuid4().hex + "@example.com"
                assert (
                    await c.post("/api/v1/auth/password-reset-codes", json={"email": unknown})
                ).json() == sent.json()
                assert (
                    await c.post(
                        "/api/v1/auth/password-reset",
                        json={
                            "email": unknown,
                            "code": mail.code(unknown),
                            "new_password": "reset-password",
                        },
                    )
                ).status_code == 204
                with Session(engine) as db:
                    assert db.scalar(select(User).where(User.email == unknown)) is None
                for _, _, message in mail.messages:
                    assert "next-password" not in message and "reset-password" not in message
                for _ in range(5):
                    assert (
                        await c.post(
                            "/api/v1/auth/login", json={"email": email, "password": "wrong"}
                        )
                    ).status_code == 401
                throttled = await c.post(
                    "/api/v1/auth/login", json={"email": email, "password": "reset-password"}
                )
                assert throttled.status_code == 429
                other_email = uuid4().hex + "@example.com"
                for _ in range(5):
                    rejected = await c.post(
                        "/api/v1/auth/login", json={"email": other_email, "password": "wrong"}
                    )
                    assert rejected.status_code == 401
                    assert rejected.json()["code"] == "invalid_credentials"
                unknown_throttled = await c.post(
                    "/api/v1/auth/login",
                    json={"email": other_email, "password": "reset-password"},
                )
                assert unknown_throttled.status_code == 429
                for field in ("code", "message", "retryable"):
                    assert unknown_throttled.json()[field] == throttled.json()[field]
                with Session(engine) as db, db.begin():
                    db.add(
                        User(
                            username="legacy-" + uuid4().hex, password_hash=password_hash("123456")
                        )
                    )
                assert (
                    await c.post(
                        "/api/v1/auth/login", json={"username": "legacy", "password": "123456"}
                    )
                ).status_code == 422
                with Session(engine) as db:
                    assert not list(
                        db.scalars(
                            select(IdentitySession).where(
                                IdentitySession.owner_id == uid,
                                IdentitySession.revoked_at.is_(None),
                                IdentitySession.token_hash == "invalid",
                            )
                        )
                    )

    asyncio.run(check())


def test_challenge_expiry_attempts_resend_quotas_and_concurrency() -> None:
    from app.database import make_engine

    engine = make_engine(os.environ["PSYEVO_TEST_DATABASE_URL"])
    key = "synthetic-key-only"
    email = uuid4().hex + "@example.com"
    try:
        with Session(engine) as db, db.begin():
            db.execute(delete(EmailCode))
            reserved = reserve_code(db, key, email, "registration")
            assert reserved
            row, code = reserved
            row.expires_at = now() - timedelta(seconds=1)
        with Session(engine) as db, db.begin():
            assert not consume_code(db, key, email, "registration", code)
            db.execute(update(EmailCode).values(created_at=now() - timedelta(minutes=2)))
        with Session(engine) as db, db.begin():
            reserved = reserve_code(db, key, email, "registration")
            assert reserved
            _, replacement = reserved
        with Session(engine) as db, db.begin():
            wrong = "000000" if replacement != "000000" else "111111"
            for _ in range(5):
                assert not consume_code(db, key, email, "registration", wrong)
            assert not consume_code(db, key, email, "registration", replacement)
        with Session(engine) as db, db.begin():
            db.execute(update(EmailCode).values(created_at=now() - timedelta(minutes=2)))
            reserved = reserve_code(db, key, email, "registration")
            assert reserved
            _, current = reserved

        def consume() -> bool:
            with Session(engine) as db, db.begin():
                return consume_code(db, key, email, "registration", current)

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(lambda _: consume(), range(2))) == [False, True]
        for _ in range(2):
            with Session(engine) as db, db.begin():
                db.execute(update(EmailCode).values(created_at=now() - timedelta(minutes=2)))
                assert reserve_code(db, key, email, "registration")
        with Session(engine) as db, db.begin():
            db.execute(update(EmailCode).values(created_at=now() - timedelta(minutes=2)))
            assert reserve_code(db, key, email, "registration") is None
            for i in range(95):
                db.add(
                    EmailCode(
                        email=f"quota-{i}@example.com",
                        purpose="registration",
                        code_hash="synthetic",
                        expires_at=now() + timedelta(minutes=10),
                    )
                )
        with Session(engine) as db, db.begin():
            assert reserve_code(db, key, "other@example.com", "registration") is None
        with Session(engine) as db, db.begin():
            db.execute(delete(EmailCode))

        def reserve() -> bool:
            with Session(engine) as db, db.begin():
                return reserve_code(db, key, email, "registration") is not None

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(lambda _: reserve(), range(2))) == [False, True]

        def insert() -> bool:
            try:
                with Session(engine) as db, db.begin():
                    db.add(User(email=email, password_hash="synthetic"))
                return True
            except IntegrityError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(lambda _: insert(), range(2))) == [False, True]
    finally:
        engine.dispose()


def test_local_cleanup_is_transactional_and_preserves_email_accounts() -> None:
    import importlib.util
    from pathlib import Path

    from app.database import make_engine
    from app.models import Conversation

    script = Path(__file__).resolve().parents[2] / "scripts/step03_local_accounts.py"
    spec = importlib.util.spec_from_file_location("local_maintenance", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = make_engine(os.environ["PSYEVO_TEST_DATABASE_URL"])
    try:
        with Session(engine) as db, db.begin():
            old = User(username="cleanup-" + uuid4().hex, password_hash="synthetic")
            keep = User(email=uuid4().hex + "@example.com", password_hash="synthetic")
            db.add_all([old, keep])
            db.flush()
            old_id, keep_id = old.id, keep.id
            db.add_all(
                [
                    Preferences(owner_id=old_id),
                    Preferences(owner_id=keep_id),
                    Conversation(owner_id=old_id),
                ]
            )
        preview = module.cleanup(engine, False)
        assert preview["expected_rows"]["users"] >= 1 and not preview["actual_rows"]
        with Session(engine) as db:
            assert db.get(User, old_id) is not None
        receipt = module.cleanup(engine, True)
        assert receipt["actual_rows"] == receipt["expected_rows"]
        with Session(engine) as db:
            assert db.get(User, old_id) is None
            assert db.get(User, keep_id) is not None
    finally:
        engine.dispose()
