"""PostgreSQL owns job leases, bounded recovery and fenced result transactions.

STEP03 exposes only a synthetic recovery probe. Real extraction is a STEP04 consumer.
"""

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter
from pydantic import Field, ValidationError
from sqlalchemy import Engine, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.api import DB, APIError, Auth, owned
from app.config import Settings
from app.contracts import Input, Version
from app.models import BackgroundJob, ContextGrant, JobBudget, User
from app.records import source_available
from app.runs import lock_owner
from app.security import digest
from app.support import Budget

router = APIRouter(prefix="/api/v1/jobs")
ACTIVE = {"queued", "running", "retry_wait"}
CONFIG_VERSION = "experiment-defaults/1"
PURPOSE: Literal["candidate_extraction"] = "candidate_extraction"
TRANSIENT = {"temporary_io", "timeout", "lease_lost"}
ERRORS = TRANSIENT | {"schema", "parameters", "permission", "deleted", "unknown_mutation"}


class JobSource(Input):
    source_type: Literal["conversation", "message", "note", "sleep_record", "support_card"]
    source_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    source_version: int = Field(gt=0, strict=True)


class BoundSource(JobSource):
    purpose: Literal["candidate_extraction"]
    grant_ref: str = Field(pattern=r"^[a-f0-9-]{36}$")
    grant_version: int = Field(gt=0, strict=True)


@dataclass(frozen=True)
class Lease:
    job_id: str
    owner_id: str
    generation: int
    token: int
    worker_id: str


def clock(db: Session) -> datetime:
    value = db.scalar(select(func.clock_timestamp()))
    assert isinstance(value, datetime)
    return value


def require_probe(settings: Settings) -> None:
    if (
        settings.environment != "test"
        or settings.support_mode != "fake"
        or not settings.database_url
    ):
        raise ValueError(
            "Job probe requires explicitly configured isolated test database/fake mode"
        )


def finish(job: BackgroundJob, status: str, reason: str | None, at: datetime) -> None:
    job.status, job.error_code = status, reason
    job.lease_owner, job.lease_until = None, None
    job.version += 1
    job.updated_at = at
    if status in {"failed", "cancelled", "invalidated", "succeeded"}:
        job.encrypted_config = None


def eligible(db: Session, job: BackgroundJob) -> bool:
    user = db.get(User, job.owner_id)
    if (
        user is None
        or user.deleted_at
        or job.deleted_at
        or job.cancelled_at
        or job.purpose != PURPOSE
        or job.kind not in {"recovery_probe", "memory_extraction"}
        or job.experiment_config_version != CONFIG_VERSION
        or not job.source_refs
    ):
        return False
    try:
        refs = [BoundSource.model_validate(ref) for ref in job.source_refs]
    except ValidationError:
        return False
    for ref in refs:
        grant = db.get(ContextGrant, ref.grant_ref)
        if (
            grant is None
            or grant.owner_id != job.owner_id
            or grant.job_id != job.id
            or grant.run_id is not None
            or grant.purpose != PURPOSE
            or grant.version != ref.grant_version
            or grant.revoked_at
            or grant.deleted_at
            or grant.source_type != ref.source_type
            or grant.source_id != ref.source_id
            or grant.source_version != ref.source_version
            or not source_available(db, grant)
        ):
            return False
    if job.kind == "memory_extraction":
        from app.memory import suppressed

        if suppressed(db, job.owner_id, job.source_refs):
            return False
    # A newer generation fences the old worker even if its lease has not expired.
    return (
        db.scalar(
            select(BackgroundJob.id)
            .where(
                BackgroundJob.owner_id == job.owner_id,
                BackgroundJob.kind == job.kind,
                BackgroundJob.source_key == job.source_key,
                BackgroundJob.generation > job.generation,
            )
            .limit(1)
        )
        is None
    )


def enqueue(
    db: Session,
    settings: Settings,
    owner: str,
    sources: list[JobSource],
    *,
    generation: int = 1,
    budget: Budget | None = None,
    max_attempts: int = 3,
    kind: Literal["recovery_probe", "memory_extraction"] = "recovery_probe",
) -> BackgroundJob:
    """Caller commits source changes, grants and job together; no HTTP auto-enqueue yet."""
    if kind == "recovery_probe":
        require_probe(settings)
    elif settings.memory_mode == "disabled":
        raise APIError(409, "memory_unavailable")
    if not 1 <= len(sources) <= 8 or generation < 1 or not 1 <= max_attempts <= 5:
        raise APIError(422, "invalid_job")
    lock_owner(db, owner)
    user = db.get(User, owner)
    if user is None or user.deleted_at:
        raise APIError(404, "not_found")
    ordered = sorted(sources, key=lambda ref: (ref.source_type, ref.source_id))
    identifiers = [(ref.source_type, ref.source_id) for ref in ordered]
    if len(set(identifiers)) != len(identifiers):
        raise APIError(422, "duplicate_source")
    key = digest(
        json.dumps(
            [ref.model_dump() for ref in ordered] if kind == "memory_extraction" else identifiers,
            sort_keys=True,
        )
    )
    previous = db.scalar(
        select(BackgroundJob)
        .where(
            BackgroundJob.owner_id == owner,
            BackgroundJob.kind == kind,
            BackgroundJob.source_key == key,
        )
        .order_by(BackgroundJob.generation.desc())
        .limit(1)
    )
    if previous is not None and generation <= previous.generation:
        expected = [ref.model_dump() for ref in ordered]
        old = [
            {k: ref[k] for k in ("source_type", "source_id", "source_version")}
            for ref in previous.source_refs
        ]
        if generation == previous.generation and old == expected:
            return previous
        raise APIError(409, "job_generation_conflict")
    if generation != (previous.generation + 1 if previous else 1):
        raise APIError(409, "job_generation_conflict")
    at = clock(db)
    if previous is None:
        limits = budget or Budget()
        account = JobBudget(
            owner_id=owner,
            limits=limits.model_dump(mode="json"),
            deadline_at=at + timedelta(seconds=limits.deadline_seconds),
        )
        db.add(account)
        db.flush()
    else:
        existing_account = db.get(JobBudget, previous.budget_ref)
        assert existing_account is not None
        account = existing_account
        if previous.status in ACTIVE:
            finish(previous, "invalidated", "generation_changed", at)
    job = BackgroundJob(
        owner_id=owner,
        kind=kind,
        purpose=PURPOSE,
        source_key=key,
        generation=generation,
        experiment_config_version=CONFIG_VERSION,
        budget_ref=account.id,
        deadline_at=account.deadline_at,
        max_attempts=previous.max_attempts if previous else max_attempts,
        attempt=previous.attempt if previous else 0,
        retention_policy_id="experiment-defaults/1",
    )
    db.add(job)
    db.flush()
    refs: list[dict[str, str | int]] = []
    for source in ordered:
        grant = ContextGrant(
            owner_id=owner,
            job_id=job.id,
            purpose=PURPOSE,
            retention_policy_id="experiment-defaults/1",
            **source.model_dump(),
        )
        if not source_available(db, grant):
            raise APIError(409, "source_unavailable")
        db.add(grant)
        db.flush()
        refs.append(
            BoundSource(
                **source.model_dump(),
                purpose=PURPOSE,
                grant_ref=grant.id,
                grant_version=grant.version,
            ).model_dump()
        )
    job.source_refs = refs
    return job


def delay(attempt: int) -> float:
    return float(min(2 ** max(0, attempt - 1), 16)) + random.uniform(0, 0.25)


def retry(job: BackgroundJob, reason: str, at: datetime) -> None:
    if job.attempt >= job.max_attempts:
        finish(job, "failed", "attempts_exhausted", at)
    elif job.deadline_at <= at:
        finish(job, "failed", "deadline", at)
    elif reason in TRANSIENT:
        finish(job, "retry_wait", reason, at)
        job.available_at = min(job.deadline_at, at + timedelta(seconds=delay(job.attempt)))
    else:
        finish(job, "failed", reason, at)


def claim(
    engine: Engine,
    worker_id: str,
    *,
    lease_seconds: float = 5,
    kind: str = "recovery_probe",
) -> Lease | None:
    if not 0 < lease_seconds <= 60 or not 1 <= len(worker_id) <= 36:
        raise ValueError("invalid_lease")
    cursor: tuple[datetime, str] | None = None
    while True:
        query = select(BackgroundJob.id, BackgroundJob.owner_id, BackgroundJob.available_at).where(
            BackgroundJob.kind == kind,
            BackgroundJob.status.in_(ACTIVE),
            or_(
                BackgroundJob.available_at <= func.clock_timestamp(),
                BackgroundJob.deadline_at <= func.clock_timestamp(),
            ),
            or_(
                BackgroundJob.status != "running",
                BackgroundJob.lease_until <= func.clock_timestamp(),
            ),
        )
        if cursor is not None:
            query = query.where(tuple_(BackgroundJob.available_at, BackgroundJob.id) > cursor)
        with Session(engine) as db:
            candidates = db.execute(
                query.order_by(BackgroundJob.available_at, BackgroundJob.id).limit(100)
            ).all()
        if not candidates:
            return None
        # Advance by the selected values, even when locks or state changes skip a batch.
        # OFFSET would miss work when earlier candidates leave the active queue.
        cursor = (candidates[-1].available_at, candidates[-1].id)
        for jid, owner, _ in candidates:
            with Session(engine) as db, db.begin():
                # Same ordering as every API mutation; SKIP LOCKED avoids head-of-line waiting.
                if (
                    db.scalar(
                        select(User.id).where(User.id == owner).with_for_update(skip_locked=True)
                    )
                    is None
                ):
                    continue
                job = db.get(BackgroundJob, jid)
                assert job is not None
                at = clock(db)
                if job.status not in ACTIVE:
                    continue
                if not eligible(db, job):
                    finish(job, "invalidated", "source_or_purpose_changed", at)
                elif job.deadline_at <= at:
                    finish(job, "failed", "deadline", at)
                elif job.status == "running":
                    if job.lease_until is not None and job.lease_until <= at:
                        job.lease_losses += 1
                        retry(job, "lease_lost", at)
                elif job.attempt >= job.max_attempts:
                    finish(job, "failed", "attempts_exhausted", at)
                elif job.available_at <= at:
                    job.status = "running"
                    job.attempt += 1
                    job.lease_token += 1
                    job.version += 1
                    job.updated_at = at
                    job.lease_owner = worker_id
                    job.lease_until = min(job.deadline_at, at + timedelta(seconds=lease_seconds))
                    return Lease(job.id, owner, job.generation, job.lease_token, worker_id)


def fenced(db: Session, lease: Lease) -> BackgroundJob | None:
    lock_owner(db, lease.owner_id)
    job = db.get(BackgroundJob, lease.job_id)
    at = clock(db)
    if (
        job is None
        or job.owner_id != lease.owner_id
        or job.status != "running"
        or job.generation != lease.generation
        or job.lease_token != lease.token
        or job.lease_owner != lease.worker_id
        or job.lease_until is None
        or job.lease_until <= at
    ):
        return None
    if not eligible(db, job):
        finish(job, "invalidated", "source_or_purpose_changed", at)
        return None
    if job.deadline_at <= at:
        finish(job, "failed", "deadline", at)
        return None
    return job


def renew(engine: Engine, lease: Lease, *, lease_seconds: float = 5) -> bool:
    if not 0 < lease_seconds <= 60:
        raise ValueError("invalid_lease")
    with Session(engine) as db, db.begin():
        job = fenced(db, lease)
        if job is None:
            return False
        job.lease_until = min(job.deadline_at, clock(db) + timedelta(seconds=lease_seconds))
        job.version += 1
        job.updated_at = clock(db)
        return True


def reserve(engine: Engine, lease: Lease, tokens: int, *, live: bool = False) -> str | None:
    """Reserve before any invocation; unknown usage retains the full reservation on recovery."""
    if type(tokens) is not int or tokens <= 0:
        raise ValueError("invalid_reservation")
    with Session(engine) as db, db.begin():
        job = fenced(db, lease)
        if job is None:
            return None
        account = db.get(JobBudget, job.budget_ref)
        assert account is not None
        limits = Budget.model_validate(account.limits)
        used = sum(int(str(c["charged_tokens"])) for c in account.calls)
        if len(account.calls) >= limits.max_calls or used + tokens > limits.max_tokens:
            finish(job, "failed", "budget_exhausted", clock(db))
            return None
        # The current handler is local fake: cost is exactly zero, not unknown vendor pricing.
        request_id = str(uuid4())
        account.calls = [
            *account.calls,
            {
                "request_id": request_id,
                "job_id": job.id,
                "generation": job.generation,
                "lease_token": lease.token,
                "attempt": job.attempt,
                "reserved_tokens": tokens,
                "charged_tokens": tokens,
                "actual_tokens": None,
                "cost": None if live else "0",
                "currency": "unknown" if live else "SYNTHETIC",
                "status": "reserved",
            },
        ]
        account.version += 1
        return request_id


def complete(
    engine: Engine,
    lease: Lease,
    request_id: str,
    actual_tokens: int | None,
    commit_result: Callable[[Session, BackgroundJob], str],
) -> bool:
    """The result writer and terminal state share one transaction, fenced before and after it."""
    with Session(engine) as db, db.begin():
        job = fenced(db, lease)
        if job is None:
            return False
        account = db.get(JobBudget, job.budget_ref)
        assert account is not None
        calls = [dict(c) for c in account.calls]
        call = next((c for c in calls if c["request_id"] == request_id), None)
        if (
            call is None
            or call["job_id"] != job.id
            or call["lease_token"] != lease.token
            or call["status"] != "reserved"
        ):
            return False
        if actual_tokens is not None and (
            type(actual_tokens) is not int
            or actual_tokens < 0
            or actual_tokens > int(str(call["reserved_tokens"]))
        ):
            finish(job, "failed", "invalid_usage", clock(db))
            return False
        call.update(
            actual_tokens=actual_tokens,
            charged_tokens=actual_tokens if actual_tokens is not None else call["reserved_tokens"],
            status="settled" if actual_tokens is not None else "usage_unknown",
        )
        limits = Budget.model_validate(account.limits)
        if (
            len(calls) > limits.max_calls
            or sum(int(str(c["charged_tokens"])) for c in calls) > limits.max_tokens
        ):
            finish(job, "failed", "budget_exhausted", clock(db))
            return False
        # Roll back the side effect if its transaction crosses the lease/deadline.
        with db.begin_nested() as write:
            result_ref = commit_result(db, job)
            db.flush()
            if fenced(db, lease) is None:
                write.rollback()
                return False
            job.result_ref = result_ref
            account.calls = calls
            account.version += 1
            finish(job, "succeeded", None, clock(db))
        return True


def fail(engine: Engine, lease: Lease, code: str) -> bool:
    # Do not persist exception messages or model/source text in the dead-letter record.
    code = code if code in ERRORS else "execution_error"
    with Session(engine) as db, db.begin():
        job = fenced(db, lease)
        if job is None:
            return False
        retry(job, code, clock(db))
        return True


def snapshot(job: BackgroundJob) -> dict[str, Any]:
    return {
        name: getattr(job, name)
        for name in (
            "id",
            "version",
            "kind",
            "generation",
            "status",
            "attempt",
            "max_attempts",
            "available_at",
            "deadline_at",
            "lease_token",
            "lease_until",
            "cancelled_at",
            "error_code",
            "result_ref",
            "budget_ref",
            "lease_losses",
        )
    }


@router.get("")
def job_summary(db: DB, auth: Auth) -> dict[str, Any]:
    rows = db.execute(
        select(
            BackgroundJob.status,
            func.count(),
            func.max(BackgroundJob.attempt),
            func.sum(BackgroundJob.lease_losses),
            func.min(BackgroundJob.created_at),
        )
        .where(BackgroundJob.owner_id == auth.owner_id)
        .group_by(BackgroundJob.status)
    ).all()
    waiting = [row[4] for row in rows if row[0] in {"queued", "retry_wait"}]
    return {
        "counts": {row[0]: row[1] for row in rows},
        "max_attempt": max((row[2] for row in rows), default=0),
        "lease_losses": sum(row[3] for row in rows),
        "oldest_wait_seconds": max(0, (clock(db) - min(waiting)).total_seconds())
        if waiting
        else None,
    }


@router.get("/{job_id}")
def get_job(job_id: str, db: DB, auth: Auth) -> dict[str, Any]:
    return snapshot(owned(db, BackgroundJob, job_id, auth.owner_id))


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, body: Version, db: DB, auth: Auth) -> dict[str, Any]:
    job = owned(db, BackgroundJob, job_id, auth.owner_id)
    if job.status == "cancelled":
        return snapshot(job)
    if job.version != body.expected_version:
        raise APIError(409, "version_conflict")
    if job.status in ACTIVE:
        job.cancelled_at = clock(db)
        finish(job, "cancelled", "user_cancelled", job.cancelled_at)
    return snapshot(job)
