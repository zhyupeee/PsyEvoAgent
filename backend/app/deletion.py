"""Durable online tombstone before retryable serial cleanup; no new worker."""

from typing import Any, Literal

from fastapi import APIRouter, Request
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.api import DB, APIError, Auth, bump, create_once, owned
from app.contracts import Version
from app.models import (
    ContextGrant,
    Conversation,
    DeletionJob,
    Feedback,
    Interaction,
    Message,
    ModelCall,
    Note,
    NoteSource,
    ProviderBinding,
    Run,
    RunBranch,
    RunEvent,
    TitleTask,
    now,
)
from app.runs import execution, lock_owner, terminal

router = APIRouter(prefix="/api/v1")
STEPS = ["online_blocked", "messages", "events", "feedback", "source_links"]


def receipt(job: DeletionJob, db: Session) -> dict[str, Any]:
    # Persisted call reservations survive deletion and process/configuration changes.
    calls = db.scalars(
        select(ModelCall)
        .join(Run, Run.id == ModelCall.run_id)
        .where(
            Run.owner_id == job.owner_id,
            Run.id.in_([run.id for run in affected_runs(db, job.target)]),
        )
    ).all()
    external = any(call.receipt.get("currency") != "SYNTHETIC" for call in calls)
    result: dict[str, Any] = {
        "deletion_id": job.id,
        "target": job.target,
        "target_type": job.target_type,
        "version": job.version,
        "status": job.status,
        "completed_steps": job.completed_steps,
        "remaining_steps": [step for step in STEPS if step not in job.completed_steps],
        "retryable": job.status != "completed",
        "error_code": job.error_code,
        "not_applicable": {
            "checkpoints": "No persistent checkpointer configured",
            "backups": "No application backup service configured",
        },
        "retained": ["content-free tombstones", "idempotency hashes", "model usage metadata"],
        "external_provider_status": "unknown" if external else "not_applicable",
    }
    if not external:
        result["not_applicable"]["external_provider"] = "No live call recorded"
    return result


def affected_runs(db: Session, target: str) -> list[Run]:
    targets = {target}
    found: dict[str, Run] = {}
    while True:
        rows = db.scalars(
            select(Run).where(
                or_(
                    Run.session_id.in_(targets),
                    Run.id.in_(
                        select(ContextGrant.run_id).where(ContextGrant.source_id.in_(targets))
                    ),
                )
            )
        ).all()
        found.update((run.id, run) for run in rows)
        note_ids = set(
            db.scalars(
                select(NoteSource.note_id)
                .join(Message, Message.id == NoteSource.message_id)
                .where(Message.run_id.in_(found))
            )
        )
        if note_ids <= targets:
            return list(found.values())
        targets.update(note_ids)


def purge_step(db: Session, job: DeletionJob, step: str) -> None:
    runs = affected_runs(db, job.target)
    ids = [run.id for run in runs]
    if step == "messages":
        for binding in db.scalars(select(ProviderBinding).where(ProviderBinding.run_id.in_(ids))):
            binding.encrypted_config = None
        db.execute(delete(TitleTask).where(TitleTask.session_id == job.target))
        for message in db.scalars(select(Message).where(Message.run_id.in_(ids))):
            message.content, message.deleted_at = "", now()
            message.source_refs, message.consent_refs = [], []
        from app.records import purge_record, source_model

        source = db.get(source_model(job.target_type), job.target)
        assert source is not None
        if isinstance(source, Conversation):
            source.title, source.source_refs, source.consent_refs = "已删除的对话", [], []
        else:
            purge_record(db, source)
        for note in db.scalars(
            select(Note).where(
                Note.id.in_(
                    select(NoteSource.note_id)
                    .join(Message, Message.id == NoteSource.message_id)
                    .where(Message.run_id.in_(ids))
                )
            )
        ):
            purge_record(db, note)
    elif step == "events":
        db.execute(delete(RunEvent).where(RunEvent.run_id.in_(ids)))
        db.execute(delete(Interaction).where(Interaction.run_id.in_(ids)))
    elif step == "feedback":
        db.execute(delete(Feedback).where(Feedback.run_id.in_(ids)))
    elif step == "source_links":
        for grant in db.scalars(
            select(ContextGrant).where(
                or_(ContextGrant.source_id == job.target, ContextGrant.run_id.in_(ids))
            )
        ):
            grant.deleted_at, grant.revoked_at = now(), now()
            grant.source_refs, grant.consent_refs = [], []
        for run in runs:
            run.source_refs, run.consent_refs = [], []
            ex = execution(db, run)
            if ex:
                ex.grant_ids, ex.source_refs, ex.consent_refs = [], [], []
        for edge in db.scalars(select(RunBranch).where(RunBranch.run_id.in_(ids))):
            edge.deleted_at, edge.source_refs, edge.consent_refs = now(), [], []


def cleanup(request: Request, job_id: str, owner: str) -> dict[str, Any]:
    # Each completed step commits independently. A crash cannot undo online blocking.
    for step in STEPS[1:]:
        with Session(request.app.state.engine) as db, db.begin():
            lock_owner(db, owner)
            job = owned(db, DeletionJob, job_id, owner)
            if step in job.completed_steps:
                continue
            try:
                with db.begin_nested():
                    purge_step(db, job, step)
                    db.flush()
            except Exception:
                job.status, job.error_code = "failed_retryable", "cleanup_" + step
                bump(job, job.version)
                result = receipt(job, db)
                return result
            job.completed_steps = [*job.completed_steps, step]
            job.status, job.error_code = "derivatives_purged", None
            bump(job, job.version)
    with Session(request.app.state.engine) as db, db.begin():
        lock_owner(db, owner)
        job = owned(db, DeletionJob, job_id, owner)
        if job.status != "completed":
            job.status, job.error_code = "completed", None
            bump(job, job.version)
        return receipt(job, db)


class DeleteSession(Version):
    confirmed: Literal[True]


@router.get("/sessions/{session_id}/deletion-preview")
def preview(session_id: str, db: DB, auth: Auth) -> dict[str, Any]:
    owned(db, Conversation, session_id, auth.owner_id)
    from app.records import related_notes

    return {
        "linked_notes": [
            {"id": note.id, "title": note.title or "未命名摘记"}
            for note in related_notes(db, [run.id for run in affected_runs(db, session_id)])
        ]
    }


@router.delete("/sessions/{session_id}", status_code=202)
def remove(
    session_id: str, body: DeleteSession, request: Request, db: DB, auth: Auth
) -> dict[str, Any]:
    def build() -> DeletionJob:
        source = owned(db, Conversation, session_id, auth.owner_id)
        bump(source, body.expected_version)
        source.deleted_at, source.status = now(), "deleted"
        source.title_generation_status = "cancelled"
        source.title_revision += 1
        for run in affected_runs(db, source.id):
            terminal(db, run, execution(db, run), "cancelled", "source_deleted")
            run.deleted_at = now()
        from app.records import related_notes

        for note in related_notes(db, [run.id for run in affected_runs(db, source.id)]):
            note.deleted_at = now()
            bump(note, note.version)
        return DeletionJob(
            owner_id=auth.owner_id,
            target=source.id,
            scope=["conversation_and_derived_runs"],
            status="online_blocked",
            completed_steps=["online_blocked"],
        )

    # Retrying an acknowledged request reuses the original receipt, even after deletion.
    job = create_once(db, request, auth, DeletionJob, body.model_dump(), build)
    job_id, owner = job.id, auth.owner_id
    db.commit()
    return cleanup(request, job_id, owner)


@router.get("/deletion-jobs/{job_id}")
def get_job(job_id: str, db: DB, auth: Auth) -> dict[str, Any]:
    return receipt(owned(db, DeletionJob, job_id, auth.owner_id), db)


@router.get("/deletion-jobs")
def jobs(db: DB, auth: Auth) -> dict[str, Any]:
    return {
        "items": [
            receipt(job, db)
            for job in db.scalars(
                select(DeletionJob)
                .where(DeletionJob.owner_id == auth.owner_id)
                .order_by(DeletionJob.created_at.desc())
                .limit(100)
            )
        ]
    }


@router.post("/deletion-jobs/{job_id}/retry")
def retry(job_id: str, body: Version, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    job = owned(db, DeletionJob, job_id, auth.owner_id)
    if job.status == "completed":
        return receipt(job, db)
    if job.version != body.expected_version:
        raise APIError(409, "version_conflict")
    owner = auth.owner_id
    db.commit()
    return cleanup(request, job_id, owner)
