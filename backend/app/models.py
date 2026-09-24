"""STEP03 persistence. No model execution, message pipeline or background consumer."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(UTC)


def opaque_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=opaque_id)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class User(Record, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "email IS NULL OR email = lower(btrim(email))", name="ck_user_email_normalized"
        ),
    )
    username: Mapped[str | None] = mapped_column(String(80), unique=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailCode(Record, Base):
    __tablename__ = "email_codes"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('registration', 'password_reset')", name="ck_email_code_purpose"
        ),
        CheckConstraint("attempts >= 0 AND attempts <= 5", name="ck_email_code_attempts"),
    )
    email: Mapped[str] = mapped_column(String(254), index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Personal(Record):
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(40), default="service_context")
    retention_policy_id: Mapped[str] = mapped_column(String(80), default="synthetic-local/1")
    source_refs: Mapped[list[dict[str, str | int]]] = mapped_column(JSONB, default=list)
    consent_refs: Mapped[list[str]] = mapped_column(JSONB, default=list)


class IdentitySession(Record, Base):
    __tablename__ = "identity_sessions"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Preferences(Personal, Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("owner_id"),
        CheckConstraint("age_band IN ('adult','minor','unknown')"),
        CheckConstraint("version > 0"),
    )
    mode: Mapped[str] = mapped_column(String(20), default="listen")
    age_band: Mapped[str] = mapped_column(String(10), default="unknown")
    age_source: Mapped[str] = mapped_column(String(20), default="not_provided")
    display_preferences: Mapped[dict[str, str | bool]] = mapped_column(JSONB, default=dict)


class Consent(Personal, Base):
    __tablename__ = "consent_records"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_consent_owner"),
        CheckConstraint(
            "purpose IN ('service_context','optional_profile','saved_memory','research')"
        ),
        CheckConstraint("decision IN ('granted','declined','revoked')"),
        CheckConstraint("purpose = 'service_context' OR decision <> 'granted'"),
        CheckConstraint("version > 0"),
    )
    notice_version: Mapped[str] = mapped_column(String(80))
    decision: Mapped[str] = mapped_column(String(10))
    scope: Mapped[list[str]] = mapped_column(JSONB)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Conversation(Personal, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        CheckConstraint("status IN ('active','archived','deleted')"),
        CheckConstraint("version > 0"),
    )
    title: Mapped[str] = mapped_column(String(120), default="新的对话")
    status: Mapped[str] = mapped_column(String(20), default="active")


class Run(Personal, Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_run_owner"),
        ForeignKeyConstraint(
            ["session_id", "owner_id"],
            ["conversations.id", "conversations.owner_id"],
            name="fk_run_session_owner",
        ),
        CheckConstraint(
            "status IN ('draft','queued','running','completed','failed','cancelled','interrupted')"
        ),
        CheckConstraint("version > 0"),
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    session_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(20), default="message")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    source_message_version: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_reason: Mapped[str | None] = mapped_column(String(60))


class ContextGrant(Personal, Base):
    __tablename__ = "context_grants"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "owner_id"], ["runs.id", "runs.owner_id"], name="fk_grant_run_owner"
        ),
        ForeignKeyConstraint(
            ["source_id", "owner_id"],
            ["conversations.id", "conversations.owner_id"],
            name="fk_grant_source_owner",
        ),
        ForeignKeyConstraint(
            ["consent_id", "owner_id"],
            ["consent_records.id", "consent_records.owner_id"],
            name="fk_grant_consent_owner",
        ),
        CheckConstraint("purpose = 'current_run'"),
        CheckConstraint("source_version > 0 AND version > 0"),
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    source_type: Mapped[str] = mapped_column(String(30), default="conversation")
    source_version: Mapped[int] = mapped_column(Integer)
    consent_id: Mapped[str | None] = mapped_column(ForeignKey("consent_records.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeletionJob(Personal, Base):
    __tablename__ = "deletion_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["target", "owner_id"],
            ["conversations.id", "conversations.owner_id"],
            name="fk_deletion_target_owner",
        ),
        CheckConstraint(
            "status IN ('requested','online_blocked','derivatives_purged',"
            "'backup_pending','completed','failed_retryable')"
        ),
    )
    target: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    scope: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(30), default="requested")
    completed_steps: Mapped[list[str]] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80))


class Idempotency(Base):
    __tablename__ = "idempotency_records"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(30))
    resource_id: Mapped[str] = mapped_column(String(36))
