"""Identity/source persistence plus STEP05 messages, execution metadata and events."""

from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
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


class ProviderSettings(Personal, Base):
    __tablename__ = "provider_settings"
    __table_args__ = (
        UniqueConstraint("owner_id"),
        CheckConstraint("mode IN ('official','custom')"),
        CheckConstraint("version > 0"),
    )
    mode: Mapped[str] = mapped_column(String(12), default="official", server_default="official")
    base_url: Mapped[str | None] = mapped_column(String(500))
    model: Mapped[str | None] = mapped_column(String(200))
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    deadline_seconds: Mapped[float] = mapped_column(default=60)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=4096)


class ProviderBinding(Base):
    """Private per-run credential snapshot, never included in public run DTOs."""

    __tablename__ = "provider_bindings"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    custom: Mapped[bool] = mapped_column(Boolean)
    encrypted_config: Mapped[str | None] = mapped_column(Text)


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
    title_source: Mapped[str] = mapped_column(
        String(12), default="default", server_default="default"
    )
    title_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    title_generation_status: Mapped[str] = mapped_column(
        String(20), default="not_requested", server_default="not_requested"
    )
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
            ["conversation_source_id", "owner_id"],
            ["conversations.id", "conversations.owner_id"],
            name="fk_grant_source_owner",
        ),
        ForeignKeyConstraint(["note_source_id", "owner_id"], ["notes.id", "notes.owner_id"]),
        ForeignKeyConstraint(
            ["sleep_source_id", "owner_id"], ["sleep_records.id", "sleep_records.owner_id"]
        ),
        ForeignKeyConstraint(
            ["card_source_id", "owner_id"], ["support_cards.id", "support_cards.owner_id"]
        ),
        CheckConstraint("source_type IN ('conversation','note','sleep_record','support_card')"),
        ForeignKeyConstraint(
            ["consent_id", "owner_id"],
            ["consent_records.id", "consent_records.owner_id"],
            name="fk_grant_consent_owner",
        ),
        ForeignKeyConstraint(
            ["job_id", "owner_id"], ["background_jobs.id", "background_jobs.owner_id"]
        ),
        CheckConstraint(
            "(purpose = 'current_run' AND run_id IS NOT NULL AND job_id IS NULL) OR "
            "(purpose = 'candidate_extraction' AND run_id IS NULL AND job_id IS NOT NULL)",
            name="ck_grant_execution_scope",
        ),
        CheckConstraint("source_version > 0 AND version > 0"),
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), index=True)
    source_id: Mapped[str] = mapped_column(String(36))
    conversation_source_id: Mapped[str | None] = mapped_column(
        String(36), Computed("CASE WHEN source_type = 'conversation' THEN source_id END")
    )
    note_source_id: Mapped[str | None] = mapped_column(
        String(36), Computed("CASE WHEN source_type = 'note' THEN source_id END")
    )
    sleep_source_id: Mapped[str | None] = mapped_column(
        String(36), Computed("CASE WHEN source_type = 'sleep_record' THEN source_id END")
    )
    card_source_id: Mapped[str | None] = mapped_column(
        String(36), Computed("CASE WHEN source_type = 'support_card' THEN source_id END")
    )
    source_type: Mapped[str] = mapped_column(String(30), default="conversation")
    source_version: Mapped[int] = mapped_column(Integer)
    consent_id: Mapped[str | None] = mapped_column(ForeignKey("consent_records.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeletionJob(Personal, Base):
    __tablename__ = "deletion_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["conversation_target_id", "owner_id"],
            ["conversations.id", "conversations.owner_id"],
            name="fk_deletion_target_owner",
        ),
        ForeignKeyConstraint(["note_target_id", "owner_id"], ["notes.id", "notes.owner_id"]),
        ForeignKeyConstraint(
            ["sleep_target_id", "owner_id"], ["sleep_records.id", "sleep_records.owner_id"]
        ),
        ForeignKeyConstraint(
            ["card_target_id", "owner_id"], ["support_cards.id", "support_cards.owner_id"]
        ),
        CheckConstraint("target_type IN ('conversation','note','sleep_record','support_card')"),
        CheckConstraint(
            "status IN ('requested','online_blocked','derivatives_purged',"
            "'backup_pending','completed','failed_retryable')"
        ),
    )
    target: Mapped[str] = mapped_column(String(36))
    target_type: Mapped[str] = mapped_column(
        String(30), default="conversation", server_default="conversation"
    )
    conversation_target_id: Mapped[str | None] = mapped_column(
        String(36), Computed("CASE WHEN target_type = 'conversation' THEN target END")
    )
    note_target_id: Mapped[str | None] = mapped_column(
        String(36), Computed("CASE WHEN target_type = 'note' THEN target END")
    )
    sleep_target_id: Mapped[str | None] = mapped_column(
        String(36), Computed("CASE WHEN target_type = 'sleep_record' THEN target END")
    )
    card_target_id: Mapped[str | None] = mapped_column(
        String(36), Computed("CASE WHEN target_type = 'support_card' THEN target END")
    )
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


class JobBudget(Record, Base):
    """Immutable limits and reservations shared by every generation of a job lineage."""

    __tablename__ = "job_budgets"
    __table_args__ = (UniqueConstraint("id", "owner_id"),)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    limits: Mapped[dict[str, object]] = mapped_column(JSONB)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    calls: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)


class BackgroundJob(Personal, Base):
    __tablename__ = "background_jobs"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        UniqueConstraint("owner_id", "kind", "source_key", "generation"),
        ForeignKeyConstraint(
            ["budget_ref", "owner_id"], ["job_budgets.id", "job_budgets.owner_id"]
        ),
        CheckConstraint("purpose = 'candidate_extraction'"),
        CheckConstraint(
            "status IN ('queued','running','retry_wait','succeeded','failed',"
            "'cancelled','invalidated')"
        ),
        CheckConstraint("version > 0 AND generation > 0 AND lease_token >= 0"),
        CheckConstraint(
            "attempt >= 0 AND max_attempts BETWEEN 1 AND 5 AND attempt <= max_attempts"
        ),
        CheckConstraint(
            "(status = 'running' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL) OR "
            "(status <> 'running' AND lease_owner IS NULL AND lease_until IS NULL)"
        ),
        Index("ix_background_jobs_recovery", "status", "available_at", "lease_until"),
    )
    kind: Mapped[str] = mapped_column(String(40))
    source_key: Mapped[str] = mapped_column(String(64))
    generation: Mapped[int] = mapped_column(Integer)
    experiment_config_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    budget_ref: Mapped[str] = mapped_column(String(36))
    lease_owner: Mapped[str | None] = mapped_column(String(36))
    lease_token: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(60))
    result_ref: Mapped[str | None] = mapped_column(String(36))
    lease_losses: Mapped[int] = mapped_column(Integer, default=0)


class Note(Personal, Base):
    __tablename__ = "notes"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        CheckConstraint("version > 0"),
        CheckConstraint("kind IN ('free','linked_excerpt')"),
        CheckConstraint("status IN ('draft','saved','needs_review','deleted')"),
        CheckConstraint("kind <> 'linked_excerpt' OR body IS NULL"),
    )
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(120), default="")
    body: Mapped[str | None] = mapped_column(Text)
    annotation: Mapped[str] = mapped_column(Text, default="")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str | None] = mapped_column(String(80))
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="saved")


class NoteSource(Base):
    __tablename__ = "note_sources"
    __table_args__ = (
        ForeignKeyConstraint(["note_id", "owner_id"], ["notes.id", "notes.owner_id"]),
        ForeignKeyConstraint(["message_id", "owner_id"], ["messages.id", "messages.owner_id"]),
        CheckConstraint("message_version > 0"),
    )
    note_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36))
    message_version: Mapped[int] = mapped_column(Integer)


class SleepRecord(Personal, Base):
    __tablename__ = "sleep_records"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        CheckConstraint("version > 0"),
        CheckConstraint("deleted_at IS NOT NULL OR entry_date IS NOT NULL"),
        CheckConstraint("interruptions IS NULL OR interruptions >= 0"),
        CheckConstraint("bed_at IS NULL OR wake_at IS NULL OR wake_at > bed_at"),
    )
    entry_date: Mapped[date | None] = mapped_column(Date)
    bed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str | None] = mapped_column(String(80))
    interruptions: Mapped[int | None] = mapped_column(Integer)
    feeling: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(Text, default="")


class SupportCard(Personal, Base):
    __tablename__ = "support_cards"
    __table_args__ = (
        UniqueConstraint("id", "owner_id"),
        UniqueConstraint("owner_id"),
        CheckConstraint("version > 0"),
    )
    helpful_methods: Mapped[str] = mapped_column(Text, default="")
    self_reminders: Mapped[str] = mapped_column(Text, default="")
    contact_notes: Mapped[str] = mapped_column(Text, default="")
    resource_refs: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    previous_content: Mapped[dict[str, object] | None] = mapped_column(JSONB)


class RunExecution(Personal, Base):
    """One durable execution per existing run; no second run state machine."""

    __tablename__ = "run_executions"
    __table_args__ = (
        UniqueConstraint("run_id"),
        ForeignKeyConstraint(["run_id", "owner_id"], ["runs.id", "runs.owner_id"]),
    )
    run_id: Mapped[str] = mapped_column(String(36))
    identity_id: Mapped[str] = mapped_column(ForeignKey("identity_sessions.id"))
    request_hash: Mapped[str] = mapped_column(String(64))
    versions: Mapped[dict[str, str]] = mapped_column(JSONB)
    budget: Mapped[dict[str, object]] = mapped_column(JSONB)
    grant_ids: Mapped[list[str]] = mapped_column(JSONB)
    preference: Mapped[str] = mapped_column(String(20))
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    generation: Mapped[int] = mapped_column(Integer, default=1)
    event_seq: Mapped[int] = mapped_column(Integer, default=0)
    event_floor: Mapped[int] = mapped_column(Integer, default=0)


class Message(Personal, Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("id", "owner_id", name="uq_message_owner"),
        ForeignKeyConstraint(["run_id", "owner_id"], ["runs.id", "runs.owner_id"]),
        UniqueConstraint("owner_id", "client_message_id"),
        UniqueConstraint("run_id", "role"),
        CheckConstraint("role IN ('user','assistant')"),
    )
    run_id: Mapped[str] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    client_message_id: Mapped[str | None] = mapped_column(String(128))


class RunEvent(Base):
    __tablename__ = "run_events"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    envelope: Mapped[dict[str, object]] = mapped_column(JSONB)


class TitleTask(Base):
    __tablename__ = "title_tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "owner_id"], ["conversations.id", "conversations.owner_id"]
        ),
        ForeignKeyConstraint(["run_id", "owner_id"], ["runs.id", "runs.owner_id"]),
    )
    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36))
    run_id: Mapped[str] = mapped_column(String(36))
    title_revision: Mapped[int] = mapped_column(Integer)
    message_versions: Mapped[dict[str, int]] = mapped_column(JSONB)
    profile: Mapped[dict[str, str]] = mapped_column(JSONB)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelCall(Base):
    __tablename__ = "model_calls"
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    receipt: Mapped[dict[str, object]] = mapped_column(JSONB)


class ProviderTest(Base):
    """One explicit synthetic probe, with no conversation or saved credential."""

    __tablename__ = "provider_tests"
    __table_args__ = (
        UniqueConstraint("owner_id", "request_key"),
        CheckConstraint("status IN ('running','completed','failed','cancelled','interrupted')"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=opaque_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    identity_id: Mapped[str] = mapped_column(ForeignKey("identity_sessions.id"))
    request_key: Mapped[str] = mapped_column(String(128))
    settings_version: Mapped[int] = mapped_column(Integer)
    custom: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")
    reason: Mapped[str | None] = mapped_column(String(80))
    receipt: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)


class Interaction(Personal, Base):
    __tablename__ = "interaction_events"
    __table_args__ = (
        UniqueConstraint("owner_id", "event_key"),
        UniqueConstraint("owner_id", "tab_id", "sequence"),
        ForeignKeyConstraint(["run_id", "owner_id"], ["runs.id", "runs.owner_id"]),
    )
    run_id: Mapped[str] = mapped_column(String(36))
    event_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(30))
    initiation: Mapped[str] = mapped_column(String(30))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    tab_id: Mapped[str | None] = mapped_column(String(64))
    sequence: Mapped[int | None] = mapped_column(Integer)
    segment: Mapped[dict[str, object] | None] = mapped_column(JSONB)


class Feedback(Personal, Base):
    __tablename__ = "feedback"
    __table_args__ = (
        ForeignKeyConstraint(["run_id", "owner_id"], ["runs.id", "runs.owner_id"]),
        CheckConstraint("helpfulness IN ('helpful','neutral','unhelpful','not_rated')"),
        CheckConstraint("category IN ('general','misunderstood','listen_only','inappropriate')"),
    )
    run_id: Mapped[str] = mapped_column(String(36))
    helpfulness: Mapped[str] = mapped_column(String(20))
    category: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text)
    notice_version: Mapped[str] = mapped_column(String(40), default="feedback-scope/1")


class RunBranch(Personal, Base):
    """An immutable revision edge; each branch reuses the existing run and messages."""

    __tablename__ = "run_branches"
    __table_args__ = (
        UniqueConstraint("run_id"),
        UniqueConstraint("parent_run_id"),
        ForeignKeyConstraint(["run_id", "owner_id"], ["runs.id", "runs.owner_id"]),
        ForeignKeyConstraint(["parent_run_id", "owner_id"], ["runs.id", "runs.owner_id"]),
        CheckConstraint("kind IN ('revision','regenerate')"),
    )
    run_id: Mapped[str] = mapped_column(String(36))
    parent_run_id: Mapped[str] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(20))
