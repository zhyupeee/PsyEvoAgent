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
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.database import make_engine
from app.models import (
    Consent,
    ContextGrant,
    Feedback,
    IdentitySession,
    LoginAttempt,
    Note,
    Personal,
    Preferences,
    ProviderTest,
    Run,
    RunBranch,
    RunExecution,
    User,
    now,
)
from app.security import password_hash
from app.support import Budget, VersionBinding


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


class Conversation(Personal, HistoricalBase):
    """Pre-title schema used to seed earlier migration revisions."""

    __tablename__ = "conversations"
    title: Mapped[str] = mapped_column(String(120), default="新的对话")
    status: Mapped[str] = mapped_column(String(20), default="active")


class HistoricalGrant(Personal, HistoricalBase):
    """Seed the pre-record schema without new generated reference columns."""

    __tablename__ = "context_grants"
    run_id: Mapped[str] = mapped_column(String(36))
    source_id: Mapped[str] = mapped_column(String(36))
    source_type: Mapped[str] = mapped_column(String(30), default="conversation")
    source_version: Mapped[int] = mapped_column(Integer)
    consent_id: Mapped[str | None] = mapped_column(String(36))


pytestmark = pytest.mark.postgres
BACKEND = Path(__file__).resolve().parents[1]


def test_provider_test_migration_retains_identity_and_refuses_receipt_loss(
    migration_url: str,
) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "j010_provider_settings")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            user = User(email="probe-migration@example.com", password_hash="synthetic")
            db.add(user)
            db.flush()
            identity = IdentitySession(
                owner_id=user.id,
                token_hash="synthetic-probe-token",
                csrf_token="synthetic",
                expires_at=now() + timedelta(hours=1),
            )
            db.add(identity)
            db.flush()
            owner, identity_id = user.id, identity.id
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as db, db.begin():
            assert db.get(IdentitySession, identity_id) is not None
            db.add(
                ProviderTest(
                    owner_id=owner,
                    identity_id=identity_id,
                    request_key="one-probe",
                    settings_version=0,
                    custom=False,
                    status="interrupted",
                    deadline_at=now(),
                    receipt={"actual_tokens": None, "reserved_tokens": 8192},
                )
            )
        with pytest.raises(RuntimeError, match="test receipts"):
            command.downgrade(config, "j010_provider_settings")
        command.check(config)
    finally:
        engine.dispose()


def test_step05_upgrade_preserves_runs_and_refuses_lossy_downgrade(migration_url: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "g034_login_attempts")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            user = User(email="step05-migration@example.com", password_hash="synthetic")
            db.add(user)
            db.flush()
            source = Conversation(owner_id=user.id)
            auth = IdentitySession(
                owner_id=user.id,
                token_hash="synthetic-unique-token",
                csrf_token="synthetic-csrf",
                expires_at=now() + timedelta(hours=1),
            )
            db.add_all([source, auth])
            db.flush()
            run = Run(owner_id=user.id, session_id=source.id, session_version=1)
            db.add(run)
            db.flush()
            rid, uid, aid = run.id, user.id, auth.id
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as db, db.begin():
            retained = db.get(Run, rid)
            assert retained is not None and retained.status == "draft" and retained.version == 1
            db.add(
                RunExecution(
                    owner_id=uid,
                    run_id=rid,
                    identity_id=aid,
                    request_hash="synthetic-request",
                    versions=VersionBinding().model_dump(),
                    budget=Budget().model_dump(mode="json"),
                    grant_ids=[],
                    preference="listen",
                    deadline_at=now() + timedelta(seconds=10),
                )
            )
        with pytest.raises(RuntimeError, match="STEP05 execution history"):
            command.downgrade(config, "g034_login_attempts")
        command.check(config)
        with Session(engine) as db:
            assert db.scalar(select(RunExecution).where(RunExecution.run_id == rid)) is not None
    finally:
        engine.dispose()


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
            grant = HistoricalGrant(
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


def test_jobs_migration_preserves_sources_and_refuses_receipt_loss(migration_url: str) -> None:
    from pydantic import SecretStr

    from app import jobs
    from app.config import Settings
    from app.models import BackgroundJob, JobBudget

    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "l012_records")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            user = User(email="jobs-migration@example.com", password_hash="preserved-hash")
            db.add(user)
            db.flush()
            note = Note(
                owner_id=user.id, body="preserved synthetic source", status="saved", kind="free"
            )
            db.add(note)
            db.flush()
            owner, nid = user.id, note.id
        command.upgrade(config, "head")
        command.downgrade(config, "l012_records")  # Empty additive tables can roll back.
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as db, db.begin():
            retained = db.get(Note, nid)
            assert retained is not None and retained.body == "preserved synthetic source"
            row = jobs.enqueue(
                db,
                Settings(
                    environment="test", support_mode="fake", database_url=SecretStr(migration_url)
                ),
                owner,
                [jobs.JobSource(source_type="note", source_id=nid, source_version=1)],
            )
            jid, bid = row.id, row.budget_ref
        with pytest.raises(RuntimeError, match="Durable job/budget receipts"):
            command.downgrade(config, "l012_records")
        with Session(engine) as db:
            assert db.get(BackgroundJob, jid) is not None
            assert db.get(JobBudget, bid) is not None
            retained_user = db.get(User, owner)
            assert retained_user is not None and retained_user.password_hash == "preserved-hash"
        command.check(config)
    finally:
        engine.dispose()


def test_records_migration_preserves_content_and_refuses_loss(migration_url: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "k011_provider_tests")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            user = User(email="record-migration@example.com", password_hash="synthetic")
            db.add(user)
            db.flush()
            owner = user.id
        command.upgrade(config, "head")
        with Session(engine) as db, db.begin():
            note = Note(
                owner_id=owner, kind="free", body="preserved synthetic draft", status="draft"
            )
            db.add(note)
            db.flush()
            note_id = note.id
        with pytest.raises(RuntimeError, match="Record/source receipts"):
            command.downgrade(config, "k011_provider_tests")
        with Session(engine) as db:
            retained = db.get(Note, note_id)
            assert retained is not None and retained.body == "preserved synthetic draft"
        command.check(config)
    finally:
        engine.dispose()


def test_empty_upgrade_is_repeatable(migration_url: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    command.check(config)
    engine = make_engine(migration_url)
    try:
        assert set(inspect(engine).get_table_names()) == {
            "background_jobs",
            "job_budgets",
            "notes",
            "note_sources",
            "sleep_records",
            "support_cards",
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
            "run_executions",
            "run_events",
            "model_calls",
            "title_tasks",
            "provider_settings",
            "provider_bindings",
            "provider_tests",
            "messages",
            "interaction_events",
            "feedback",
            "run_branches",
        }
    finally:
        engine.dispose()


def test_title_migration_preserves_titles_and_provenance(migration_url: str) -> None:
    from app.models import Conversation as CurrentConversation

    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "h007_history_feedback")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            user = User(email="title-migration@example.com", password_hash="synthetic")
            db.add(user)
            db.flush()
            default = Conversation(owner_id=user.id)
            manual = Conversation(owner_id=user.id, title="保留手动主题")
            db.add_all([default, manual])
            db.flush()
            ids = default.id, manual.id
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as db, db.begin():
            rows = [db.get(CurrentConversation, sid) for sid in ids]
            assert all(row is not None for row in rows)
            assert [(row.title, row.title_source) for row in rows if row] == [
                ("新的对话", "default"),
                ("保留手动主题", "manual"),
            ]
            assert rows[0] is not None
            rows[0].title_revision = 2
        with pytest.raises(RuntimeError, match="automatic title history"):
            command.downgrade(config, "h007_history_feedback")
        command.check(config)
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
                == "m013_background_jobs"
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


@pytest.mark.parametrize("kind", ["feedback", "branch"])
def test_step07_upgrade_preserves_history_and_refuses_loss(migration_url: str, kind: str) -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "d642b94fcbb5")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            user = User(email="step07-migration@example.com", password_hash="synthetic")
            db.add(user)
            db.flush()
            source = Conversation(owner_id=user.id, title="保留原始会话")
            db.add(source)
            db.flush()
            run = Run(owner_id=user.id, session_id=source.id, session_version=1, status="completed")
            db.add(run)
            db.flush()
            uid, sid, rid = user.id, source.id, run.id
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as db, db.begin():
            retained = db.get(Conversation, sid)
            assert (
                retained is not None and retained.title == "保留原始会话" and retained.version == 1
            )
            if kind == "feedback":
                db.add(
                    Feedback(owner_id=uid, run_id=rid, helpfulness="helpful", category="general")
                )
            else:
                new = Run(owner_id=uid, session_id=sid, session_version=1)
                db.add(new)
                db.flush()
                db.add(RunBranch(owner_id=uid, run_id=new.id, parent_run_id=rid, kind="revision"))
        with pytest.raises(RuntimeError, match="STEP07 history"):
            command.downgrade(config, "d642b94fcbb5")
        command.check(config)
    finally:
        engine.dispose()
