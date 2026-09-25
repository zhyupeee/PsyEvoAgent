"""STEP05 durable run operations. Only the standalone worker invokes Support."""

import logging
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import AwareDatetime, Field, field_validator, model_validator
from sqlalchemy import Engine, delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api import DB, APIError, Auth, create_once, owned, resource
from app.contracts import Input, Version
from app.models import (
    ContextGrant,
    Conversation,
    IdentitySession,
    Interaction,
    Message,
    ModelCall,
    Preferences,
    Run,
    RunEvent,
    RunExecution,
    User,
    now,
)
from app.security import digest
from app.support import Budget, VersionBinding

router = APIRouter(prefix="/api/v1")
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}
EVENT_WINDOW = 128


class RunInput(Input):
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Blank message")
        if "\x00" in value:
            raise ValueError("Message contains NUL")
        return value


class Start(Version):
    input: RunInput
    expected_session_version: int = Field(gt=0, strict=True)
    client_message_id: str = Field(min_length=1, max_length=128, pattern=r"^[\w-]+$")
    grant_ids: list[str] = Field(default_factory=list, max_length=8)
    initiation: Literal["user", "requested_followup", "unknown"] = "user"


class Send(Start):
    kind: Literal["message"] = "message"
    expected_version: Literal[1] = 1


def execution(db: Session, run: Run) -> RunExecution | None:
    return db.scalar(select(RunExecution).where(RunExecution.run_id == run.id))


def lock_owner(db: Session, owner: str) -> None:
    db.execute(select(User.id).where(User.id == owner).with_for_update())


def sources_available(db: Session, run: Run, ex: RunExecution | None) -> bool:
    source = db.get(Conversation, run.session_id)
    if (
        source is None
        or source.owner_id != run.owner_id
        or source.deleted_at
        or source.status != "active"
    ):
        return False
    if ex is None:
        return True
    # Source versions are fixed at start; title/source edits conservatively invalidate output.
    if source.version != run.session_version:
        return False
    if run.status != "draft":
        messages = db.scalars(select(Message).where(Message.run_id == run.id)).all()
        source_message = next((m for m in messages if m.role == "user"), None)
        if (
            source_message is None
            or source_message.version != run.source_message_version
            or any(m.deleted_at or m.owner_id != run.owner_id for m in messages)
        ):
            return False
    for gid in ex.grant_ids:
        grant = db.get(ContextGrant, gid)
        if (
            grant is None
            or grant.owner_id != run.owner_id
            or grant.run_id != run.id
            or grant.revoked_at
            or grant.deleted_at
            or grant.purpose != "current_run"
        ):
            return False
        source = db.get(Conversation, grant.source_id)
        if (
            source is None
            or source.owner_id != run.owner_id
            or source.deleted_at
            or source.status != "active"
            or source.version != grant.source_version
        ):
            return False
    return True


def executable(db: Session, run: Run, ex: RunExecution) -> bool:
    auth = db.get(IdentitySession, ex.identity_id)
    user = db.get(User, run.owner_id)
    return bool(
        user
        and user.email
        and not user.deleted_at
        and auth
        and not auth.revoked_at
        and auth.owner_id == run.owner_id
        and auth.expires_at > now()
        and run.status == "running"
        and not run.deleted_at
        and ex.deadline_at > now()
        and sources_available(db, run, ex)
    )


def emit(db: Session, run: Run, ex: RunExecution, event_type: str, payload: dict[str, Any]) -> None:
    ex.event_seq += 1
    db.add(
        RunEvent(
            run_id=run.id,
            event_id=ex.event_seq,
            envelope={
                "schema_version": "public-run-events/1",
                "run_id": run.id,
                "event_id": str(ex.event_seq),
                "generation": ex.generation,
                "type": event_type,
                "run_version": run.version,
                "occurred_at": now().isoformat(),
                "payload": payload,
            },
        )
    )
    ex.event_floor = max(0, ex.event_seq - EVENT_WINDOW)
    db.execute(
        delete(RunEvent).where(RunEvent.run_id == run.id, RunEvent.event_id <= ex.event_floor)
    )


def terminal(
    db: Session, run: Run, ex: RunExecution | None, status: str, reason: str | None
) -> bool:
    """Caller holds owner lock; conditional update also fences stale/late completion."""
    if run.status in TERMINAL:
        return False
    previous = run.version
    changed = db.execute(
        update(Run)
        .where(Run.id == run.id, Run.version == previous, Run.status.not_in(TERMINAL))
        .values(status=status, version=previous + 1, stop_reason=reason, updated_at=now())
        .returning(Run.id)
    ).scalar_one_or_none()
    if changed is None:
        return False
    db.refresh(run)
    if ex is not None:
        if status != "completed":
            ex.generation += 1
        event_type = "run.failed" if status == "interrupted" else "run." + status
        emit(db, run, ex, event_type, {"stop_reason": reason})
    return True


def snapshot(db: Session, run: Run) -> dict[str, Any]:
    ex = execution(db, run)
    if not sources_available(db, run, ex):
        raise APIError(404, "not_found")
    output = db.scalar(
        select(Message).where(
            Message.run_id == run.id, Message.role == "assistant", Message.deleted_at.is_(None)
        )
    )
    calls = db.scalars(select(ModelCall).where(ModelCall.run_id == run.id)).all()
    unknown = any(call.receipt.get("actual_tokens") is None for call in calls)
    used = sum(
        int(
            str(
                call.receipt.get("actual_tokens")
                if call.receipt.get("actual_tokens") is not None
                else call.receipt["reserved_tokens"]
            )
        )
        for call in calls
    )
    return {
        **resource(run),
        "generation": ex.generation if ex else 0,
        "last_event_id": str(ex.event_seq) if ex else "0",
        "version_binding": ex.versions if ex else None,
        "budget": ex.budget if ex else None,
        "budget_used": {"calls": len(calls), "accounted_tokens": used, "usage_unknown": unknown},
        "deadline_at": ex.deadline_at.isoformat() if ex else None,
        "output": {"id": output.id, "version": output.version, "text": output.content}
        if output is not None and run.status == "completed"
        else None,
    }


def start_run(
    db: Session, run: Run, body: Start, request: Request, identity: IdentitySession
) -> Run:
    fingerprint = digest(body.model_dump_json())
    ex = execution(db, run)
    if ex is not None:
        if ex.request_hash != fingerprint:
            raise APIError(409, "idempotency_conflict")
        if not sources_available(db, run, ex):
            raise APIError(404, "not_found")
        return run
    if request.app.state.settings.support_mode != "fake":
        raise APIError(503, "provider_not_configured")
    if run.status != "draft" or run.version != body.expected_version:
        raise APIError(409, "version_conflict")
    source = owned(db, Conversation, run.session_id, identity.owner_id)
    if (
        source.version != body.expected_session_version
        or source.version != run.session_version
        or source.status != "active"
    ):
        raise APIError(409, "version_conflict")
    if len(set(body.grant_ids)) != len(body.grant_ids):
        raise APIError(422, "duplicate_grant")
    for grant_id in body.grant_ids:
        owned(db, ContextGrant, grant_id, run.owner_id)
    if db.scalar(
        select(Message.id).where(
            Message.owner_id == run.owner_id, Message.client_message_id == body.client_message_id
        )
    ):
        raise APIError(409, "client_message_conflict")
    if db.scalar(
        select(Run.id).where(
            Run.session_id == run.session_id, Run.status.in_({"queued", "running"})
        )
    ):
        raise APIError(409, "run_active")
    pref = db.scalar(select(Preferences).where(Preferences.owner_id == run.owner_id))
    ex = RunExecution(
        owner_id=run.owner_id,
        run_id=run.id,
        identity_id=identity.id,
        request_hash=fingerprint,
        grant_ids=body.grant_ids,
        versions=VersionBinding().model_dump(),
        budget=Budget().model_dump(mode="json"),
        preference=pref.mode if pref else "listen",
        deadline_at=now() + timedelta(seconds=10),
    )
    if not sources_available(db, run, ex):
        raise APIError(403, "grant_inactive")
    db.add(ex)
    run.status, run.version, run.source_message_version = "queued", run.version + 1, 1
    run.updated_at = now()
    db.add(
        Message(
            owner_id=run.owner_id,
            run_id=run.id,
            role="user",
            content=body.input.message,
            client_message_id=body.client_message_id,
        )
    )
    db.flush()
    try:
        with db.begin_nested():
            db.add(
                Interaction(
                    owner_id=run.owner_id,
                    run_id=run.id,
                    event_key=(
                        "send:" + body.client_message_id
                        if len(body.client_message_id) <= 123
                        else "send:sha256:" + digest(body.client_message_id)
                    ),
                    request_hash=fingerprint,
                    event_type="message_sent",
                    initiation=body.initiation,
                    occurred_at=now(),
                )
            )
            db.flush()
    except SQLAlchemyError:
        logging.getLogger("uvicorn.error").warning("interaction.unavailable")
    return run


@router.post("/runs/{run_id}/start", status_code=202)
def start(run_id: str, body: Start, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    run = owned(db, Run, run_id, auth.owner_id)
    row = create_once(
        db, request, auth, Run, body.model_dump(), lambda: start_run(db, run, body, request, auth)
    )
    # Idempotency replay must still check the original input and current sources.
    return snapshot(db, start_run(db, row, body, request, auth))


@router.post("/sessions/{session_id}/runs", status_code=202)
def send(session_id: str, body: Send, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    def build() -> Run:
        prior = db.scalar(
            select(Message).where(
                Message.owner_id == auth.owner_id,
                Message.client_message_id == body.client_message_id,
            )
        )
        if prior is not None:
            run = owned(db, Run, prior.run_id, auth.owner_id)
            if run.session_id != session_id:
                raise APIError(409, "client_message_conflict")
            return start_run(db, run, body, request, auth)
        run = Run(
            owner_id=auth.owner_id,
            session_id=session_id,
            session_version=body.expected_session_version,
        )
        owned(db, Conversation, session_id, auth.owner_id)
        db.add(run)
        db.flush()
        return start_run(db, run, body, request, auth)

    return snapshot(db, create_once(db, request, auth, Run, body.model_dump(), build))


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: str, body: Version, db: DB, auth: Auth) -> dict[str, Any]:
    run = owned(db, Run, run_id, auth.owner_id)
    owned(db, Conversation, run.session_id, auth.owner_id)
    if run.status not in TERMINAL:
        if body.expected_version != run.version:
            raise APIError(409, "version_conflict")
        terminal(db, run, execution(db, run), "cancelled", "user_cancelled")
    return resource(run)


class ActiveSegment(Input):
    tab_id: str = Field(min_length=1, max_length=64)
    sequence: int = Field(ge=0, strict=True)
    start_ms: int = Field(ge=0, strict=True)
    end_ms: int = Field(ge=0, strict=True)
    visible: bool
    focused: bool

    @model_validator(mode="after")
    def ordered(self) -> "ActiveSegment":
        if not 0 <= self.end_ms - self.start_ms <= 30000:
            raise ValueError("Invalid active interval")
        return self


class InteractionInput(Input):
    event_id: str = Field(min_length=1, max_length=100)
    run_id: str = Field(min_length=1, max_length=36)
    event_type: Literal["session_opened", "active_segment"]
    initiation: Literal["user", "requested_followup", "system_push", "unknown"] = "unknown"
    occurred_at: AwareDatetime
    segment: ActiveSegment | None = None

    @model_validator(mode="after")
    def segment_required(self) -> "InteractionInput":
        if (self.event_type == "active_segment") != (self.segment is not None):
            raise ValueError("Segment mismatch")
        return self


class InteractionBatch(Input):
    events: list[InteractionInput] = Field(min_length=1, max_length=50)


def merge_intervals(intervals: list[tuple[int, int]]) -> int:
    total, end = 0, -1
    for start, stop in sorted(intervals):
        total += max(0, stop - max(start, end))
        end = max(end, stop)
    return total


@router.post("/interaction-events")
def interactions(body: InteractionBatch, db: DB, auth: Auth) -> dict[str, Any]:
    counts = {"accepted": 0, "duplicate": 0, "rejected": 0}
    for event in body.events:
        run = owned(db, Run, event.run_id, auth.owner_id)
        if not sources_available(db, run, execution(db, run)):
            raise APIError(404, "not_found")
        key, fingerprint = "event:" + event.event_id, digest(event.model_dump_json())
        previous = db.scalar(
            select(Interaction).where(
                Interaction.owner_id == auth.owner_id, Interaction.event_key == key
            )
        )
        if previous:
            counts["duplicate" if previous.request_hash == fingerprint else "rejected"] += 1
            continue
        segment = event.segment
        if abs((now() - event.occurred_at).total_seconds()) > 300:
            counts["rejected"] += 1
            continue
        if segment and db.scalar(
            select(Interaction.id).where(
                Interaction.owner_id == auth.owner_id,
                Interaction.tab_id == segment.tab_id,
                Interaction.sequence >= segment.sequence,
            )
        ):
            counts["rejected"] += 1
            continue
        db.add(
            Interaction(
                owner_id=auth.owner_id,
                run_id=run.id,
                event_key=key,
                request_hash=fingerprint,
                event_type=event.event_type,
                initiation=event.initiation,
                occurred_at=event.occurred_at,
                tab_id=segment.tab_id if segment else None,
                sequence=segment.sequence if segment else None,
                segment=segment.model_dump() if segment else None,
            )
        )
        db.flush()
        counts["accepted"] += 1
    # No calibrated common clock across tabs yet: do not manufacture measured attention.
    intervals: list[tuple[int, int]] = []
    rows = db.scalars(
        select(Interaction)
        .where(
            Interaction.owner_id == auth.owner_id,
            Interaction.run_id.in_({event.run_id for event in body.events}),
            Interaction.event_type == "active_segment",
        )
        .order_by(Interaction.received_at.desc())
        .limit(1001)
    ).all()
    for row in rows[:1000]:
        if row.segment is not None:
            segment_value = ActiveSegment.model_validate(row.segment)
            if segment_value.visible and segment_value.focused:
                # Wall anchor is only a reported alignment, not calibrated real attention.
                end = int(row.occurred_at.timestamp() * 1000)
                intervals.append((end - (segment_value.end_ms - segment_value.start_ms), end))
    return {
        **counts,
        "active_ms": None,
        "coverage": "uncalibrated",
        "reported_union_ms": merge_intervals(intervals),
        "truncated": len(rows) > 1000,
    }


def stop_identity_runs(db: Session, identity_id: str) -> None:
    for run in db.scalars(
        select(Run)
        .join(RunExecution, RunExecution.run_id == Run.id)
        .where(RunExecution.identity_id == identity_id, Run.status.in_({"queued", "running"}))
    ):
        terminal(db, run, execution(db, run), "cancelled", "identity_revoked")


def authorized_event(
    engine: Engine,
    owner: str,
    identity_id: str,
    run_id: str,
    cursor: int,
    generation: int | None = None,
) -> tuple[dict[str, Any] | None, bool, int]:
    with Session(engine) as db, db.begin():
        lock_owner(db, owner)
        auth = db.get(IdentitySession, identity_id)
        user = db.get(User, owner)
        if (
            not auth
            or auth.owner_id != owner
            or auth.revoked_at
            or auth.expires_at <= now()
            or not user
            or user.deleted_at
        ):
            raise APIError(401, "authentication_required")
        run = owned(db, Run, run_id, owner)
        ex = execution(db, run)
        if not sources_available(db, run, ex):
            raise APIError(404, "not_found")
        seq, floor, current = (ex.event_seq, ex.event_floor, ex.generation) if ex else (0, 0, 0)
        if cursor < floor:
            raise APIError(410, "event_cursor_expired")
        if cursor > seq:
            raise APIError(422, "invalid_cursor")
        if generation is not None and generation != current:
            # End this subscription; reconnect uses current authorized generation.
            return None, True, current
        event = db.scalar(
            select(RunEvent)
            .where(RunEvent.run_id == run.id, RunEvent.event_id > cursor)
            .order_by(RunEvent.event_id)
            .limit(1)
        )
        data = event.envelope if event else None
        if data and data.get("type") == "message.delta" and data.get("generation") != current:
            return None, True, current
        return data, run.status in TERMINAL or run.status == "draft", current
