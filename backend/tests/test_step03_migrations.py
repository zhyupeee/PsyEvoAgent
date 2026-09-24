import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import Column, DateTime, Integer, String, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session

from app.database import make_engine
from app.models import (
    Consent,
    ContextGrant,
    Conversation,
    LoginAttempt,
    Preferences,
    Run,
    User,
    now,
)
from app.security import password_hash


class HistoricalBase(DeclarativeBase):
    pass


class HistoricalUser(HistoricalBase):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username = Column(String(80))
    password_hash = Column(String(256))
    schema_version = Column(Integer, default=1)
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), default=now)
    updated_at = Column(DateTime(timezone=True), default=now)
    failed_logins = Column(Integer, default=0)


pytestmark = pytest.mark.postgres
BACKEND = Path(__file__).resolve().parents[1]


def test_default_configuration_migration_preserves_history(migration_url: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "d031_experiment_expiry")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            user = HistoricalUser(username="legacy-defaults", password_hash=password_hash("123456"))
            db.add(user)
            db.flush()
            uid, old_hash = user.id, user.password_hash
            db.add(Preferences(owner_id=uid, age_band="minor", age_source="self_reported"))
            source = Conversation(owner_id=uid)
            consent = Consent(
                owner_id=uid,
                decision="declined",
                purpose="service_context",
                notice_version="synthetic-notice/1",
                scope=["current_run"],
            )
            db.add_all([source, consent])
            db.flush()
            run = Run(owner_id=uid, session_id=source.id, session_version=1)
            db.add(run)
            db.flush()
            grant = ContextGrant(
                owner_id=uid,
                purpose="current_run",
                source_id=source.id,
                source_version=1,
                run_id=run.id,
                consent_id=consent.id,
                consent_refs=[consent.id],
            )
            db.add(grant)
            db.flush()
            cid, gid, sid, rid = consent.id, grant.id, source.id, run.id
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as db, db.begin():
            retained = db.get(User, uid)
            assert retained is not None and retained.password_hash == old_hash
            pref = db.scalar(select(Preferences).where(Preferences.owner_id == uid))
            assert pref is not None and pref.age_band == "minor"
            rows = list(db.scalars(select(Consent).where(Consent.owner_id == uid)))
            assert len(rows) == 1 and rows[0].id == cid and rows[0].decision == "declined"
            old = db.get(ContextGrant, gid)
            assert old is not None and old.consent_id == cid and old.consent_refs == [cid]
            from app.api import grant_valid

            assert grant_valid(db, old)
            db.add(
                ContextGrant(
                    owner_id=uid, purpose="current_run", source_id=sid, source_version=1, run_id=rid
                )
            )
        with pytest.raises(RuntimeError, match="historical consent"):
            command.downgrade(config, "d031_experiment_expiry")
        command.check(config)
    finally:
        engine.dispose()


@pytest.fixture
def migration_url(monkeypatch: pytest.MonkeyPatch) -> str:
    url = make_url(os.environ["PSYEVO_TEST_DATABASE_URL"])
    name = "psyevo_synthetic_migration_" + uuid4().hex
    with psycopg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False), autocommit=True
    ) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    value = url.set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("PSYEVO_DATABASE_URL", value)
    return value


def test_empty_upgrade_is_repeatable(migration_url: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)
    engine = make_engine(migration_url)
    try:
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "users",
            "email_codes",
            "login_attempts",
            "identity_sessions",
            "user_preferences",
            "consent_records",
            "conversations",
            "runs",
            "context_grants",
            "deletion_jobs",
            "idempotency_records",
        }
    finally:
        engine.dispose()


def test_previous_schema_upgrade_and_downgrade_preserve_data(migration_url: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "7af8981db341")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            user = HistoricalUser(
                username="migration-owner", password_hash=password_hash("synthetic-password")
            )
            db.add(user)
            db.flush()
            uid = user.id
            db.add(Preferences(owner_id=uid, age_band="minor", age_source="self_reported"))
            row = Conversation(owner_id=uid, title="synthetic-upgrade-preserved")
            db.add(row)
            db.flush()
            sid = row.id
        # Current ORM is readable against N-1 before additive constraints are applied.
        with Session(engine) as db:
            assert db.get(Conversation, sid) is not None
        command.upgrade(config, "head")
        command.check(config)
        command.downgrade(config, "7af8981db341")
        with Session(engine) as db:
            retained = db.get(Conversation, sid)
            assert retained is not None and retained.title == "synthetic-upgrade-preserved"
            pref = db.scalar(select(Preferences).where(Preferences.owner_id == uid))
            assert pref is not None and pref.age_band == "minor"
        command.upgrade(config, "head")
        with Session(engine) as db:
            assert db.get(Conversation, sid) is not None
    finally:
        engine.dispose()


def test_failed_owner_constraint_upgrade_rolls_back_and_can_recover(migration_url: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "7af8981db341")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            a = HistoricalUser(username="owner-a", password_hash="synthetic-only")
            b = HistoricalUser(username="owner-b", password_hash="synthetic-only")
            db.add_all([a, b])
            db.flush()
            source = Conversation(owner_id=a.id)
            db.add(source)
            db.flush()
            invalid = Run(
                owner_id=b.id,
                session_id=source.id,
                session_version=1,
                expires_at=now() + timedelta(minutes=30),
            )
            db.add(invalid)
            db.flush()
            rid, aid = invalid.id, a.id
        with pytest.raises(IntegrityError):
            command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version")) == "7af8981db341"
            )
        assert not any(
            fk["name"] == "fk_run_session_owner" for fk in inspect(engine).get_foreign_keys("runs")
        )
        with Session(engine) as db, db.begin():
            recovered = db.get(Run, rid)
            assert recovered is not None
            recovered.owner_id = aid
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as db:
            assert db.get(Run, rid) is not None
    finally:
        engine.dispose()


def test_no_expiry_migration_preserves_records_and_refuses_lossy_downgrade(
    migration_url: str,
) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "c1756470d092")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            user = HistoricalUser(username="expiry-migration", password_hash="synthetic-only")
            db.add(user)
            db.flush()
            source = Conversation(owner_id=user.id)
            db.add(source)
            db.flush()
            old = Run(
                owner_id=user.id,
                session_id=source.id,
                session_version=1,
                expires_at=now() - timedelta(days=365),
            )
            db.add(old)
            db.flush()
            rid, uid, sid = old.id, user.id, source.id
        command.upgrade(config, "head")
        with Session(engine) as db, db.begin():
            retained = db.get(Run, rid)
            assert retained is not None and retained.expires_at is not None
            db.add(Run(owner_id=uid, session_id=sid, session_version=1))
        with pytest.raises(RuntimeError, match="mandatory expiry"):
            command.downgrade(config, "c1756470d092")
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "g034_login_attempts"
            )
        command.check(config)
    finally:
        engine.dispose()


def test_email_migration_preserves_legacy_and_refuses_lossy_downgrade(migration_url: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "e032_experiment_defaults")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            legacy = HistoricalUser(username="preserved-legacy", password_hash="unchanged-hash")
            db.add(legacy)
            db.flush()
            legacy_id = legacy.id
            db.add(Preferences(owner_id=legacy_id))
        command.upgrade(config, "head")
        with Session(engine) as db, db.begin():
            retained = db.get(User, legacy_id)
            assert retained is not None and retained.email is None
            assert (
                retained.username == "preserved-legacy"
                and retained.password_hash == "unchanged-hash"
            )
            db.add(User(email="new@example.com", password_hash="new-synthetic-hash"))
        with pytest.raises(RuntimeError, match="email identities"):
            command.downgrade(config, "e032_experiment_defaults")
        command.check(config)
        with Session(engine) as db:
            assert db.scalar(select(User).where(User.email == "new@example.com")) is not None
    finally:
        engine.dispose()


def test_login_attempt_migration_preserves_existing_lockout(migration_url: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "f033_email_identity")
    engine = make_engine(migration_url)
    try:
        deadline = now() + timedelta(minutes=1)
        with Session(engine) as db, db.begin():
            db.add(
                User(
                    email="locked@example.com",
                    password_hash="synthetic-only",
                    failed_logins=4,
                    locked_until=deadline,
                )
            )
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as db:
            attempt = db.get(LoginAttempt, "locked@example.com")
            assert attempt is not None
            assert attempt.failed_logins == 4 and attempt.locked_until == deadline
        with pytest.raises(RuntimeError, match="login throttle history"):
            command.downgrade(config, "f033_email_identity")
    finally:
        engine.dispose()
