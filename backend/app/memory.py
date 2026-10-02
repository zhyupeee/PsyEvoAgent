"""Memory service: source-bound jobs and one canonical, fenced save transaction."""

from importlib.metadata import version
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import jobs
from app.api import DB, APIError, Auth, bump, create_once, owned, resource
from app.config import Settings
from app.contracts import Input, Version
from app.memory_models import ArtifactSource, Memory, MemoryCandidate, MemorySuppression
from app.models import BackgroundJob, ContextGrant, DeletionJob, Message, Note, Personal, now
from app.records import dto, excerpt_messages, mutation_receipt, source_available, source_model
from app.security import digest
from app.support import Budget

router = APIRouter(prefix="/api/v1")
GENERATOR = "langmem/" + version("langmem") + ":memory-json/1"


class Proposal(Input):
    """A sourced memory proposal, never an instruction or a user confirmation."""

    content: str = Field(min_length=1, max_length=1200)
    claim_type: Literal["user_statement", "user_feeling", "system_inference"]
    source_ids: list[str] = Field(min_length=1, max_length=8)
    evidence: str = Field(min_length=1, max_length=1200)
    event_time: AwareDatetime | None = None

    @field_validator("content", "evidence")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank_proposal")
        return value


class ProposalBatch(Input):
    memories: list[Proposal] = Field(max_length=4)


def source_key(ref: dict[str, Any]) -> str:
    return digest(str(ref["source_type"]) + ":" + str(ref["source_id"]))


def suppressed(db: Session, owner: str, refs: list[dict[str, Any]]) -> bool:
    refs = list(refs)
    for ref in list(refs):
        if ref["source_type"] == "note":
            note = db.get(Note, str(ref["source_id"]))
            if note is not None and note.owner_id == owner:
                refs.extend(note.source_refs)
    return (
        db.scalar(
            select(MemorySuppression.id)
            .where(
                MemorySuppression.owner_id == owner,
                MemorySuppression.source_key.in_([source_key(ref) for ref in refs]),
            )
            .limit(1)
        )
        is not None
    )


def source_payload(db: Session, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for ref in refs:
        row = db.get(source_model(str(ref["source_type"])), str(ref["source_id"]))
        if row is None:
            raise ValueError("source_unavailable")
        if isinstance(row, Message):
            content: Any = row.content
            user_text = row.content if row.role == "user" else ""
        else:
            value = dto(db, row)
            keys = {
                "note": ("title", "body", "annotation", "source_messages", "occurred_at"),
                "sleep_record": (
                    "entry_date",
                    "bed_at",
                    "wake_at",
                    "timezone",
                    "interruptions",
                    "feeling",
                    "note",
                ),
                "support_card": ("helpful_methods", "self_reminders", "contact_notes"),
            }.get(str(ref["source_type"]))
            if keys is None:
                raise ValueError("explicit_message_sources_required")
            content = {key: value[key] for key in keys}
            if isinstance(row, Note) and row.kind == "linked_excerpt":
                user_text = (
                    row.annotation
                    + "\n"
                    + "\n".join(
                        m.content for m in excerpt_messages(db, row) or [] if m.role == "user"
                    )
                )
            else:
                user_text = "\n".join(
                    str(value[k]) for k in keys if isinstance(value[k], str) and value[k].strip()
                )
        result.append({**ref, "content": content, "user_text": user_text})
    return result


def enqueue_sources(
    db: Session, settings: Settings, owner: str, sources: list[jobs.JobSource]
) -> BackgroundJob:
    if any(s.source_type == "conversation" for s in sources):
        raise APIError(422, "explicit_message_sources_required")
    if suppressed(db, owner, [s.model_dump() for s in sources]):
        raise APIError(409, "memory_source_suppressed")
    job = jobs.enqueue(
        db,
        settings,
        owner,
        sources,
        kind="memory_extraction",
        budget=Budget(max_tokens=32768, max_cost=None, deadline_seconds=120),
    )
    if not job.provider_profile:
        from app.provider_settings import encrypt, for_owner

        try:
            selected = (
                for_owner(db, settings, owner) if settings.memory_mode == "live" else settings
            )
        except ValueError:
            jobs.finish(job, "failed", "provider_configuration", jobs.clock(db))
            return job
        job.provider_profile = {
            "mode": settings.memory_mode,
            "model": selected.provider_model,
            "base_url": selected.provider_base_url,
            "generator": GENERATOR,
            "adapter": version("langchain-openai"),
            "schema": "memory-proposal/1",
        }
        if selected.provider_encryption_key and selected.provider_api_key:
            job.encrypted_config = encrypt(
                selected,
                owner,
                job.id,
                {
                    "provider_api_key": selected.provider_api_key.get_secret_value(),
                    "provider_base_url": selected.provider_base_url,
                    "provider_model": selected.provider_model,
                    "provider_custom_endpoint": selected.provider_custom_endpoint,
                },
            )
    return job


def auto_enqueue(db: Session, settings: Settings, row: Personal) -> None:
    if settings.memory_mode == "disabled":
        return
    kind = {
        "Note": "note",
        "SleepRecord": "sleep_record",
        "SupportCard": "support_card",
        "Message": "message",
    }.get(type(row).__name__)
    if kind is None or (isinstance(row, Note) and row.status != "saved"):
        return
    db.flush()
    source = jobs.JobSource.model_validate(
        {"source_type": kind, "source_id": row.id, "source_version": row.version}
    )
    if suppressed(db, row.owner_id, [source.model_dump()]):
        return
    # No Provider call here. Source + job + grants commit together.
    enqueue_sources(db, settings, row.owner_id, [source])


def validate_proposals(db: Session, job: BackgroundJob, batch: ProposalBatch) -> None:
    keys = [
        (item.content, item.claim_type, tuple(sorted(item.source_ids))) for item in batch.memories
    ]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate_candidate")
    payload = source_payload(db, job.source_refs)
    by_id = {str(item["source_id"]): item for item in payload}
    for item in batch.memories:
        if len(set(item.source_ids)) != len(item.source_ids) or any(
            s not in by_id for s in item.source_ids
        ):
            raise ValueError("unknown_source")
        field = "user_text" if item.claim_type != "system_inference" else "content"
        if not any(item.evidence in str(by_id[s][field]) for s in item.source_ids):
            raise ValueError("unsupported_claim")
        # Auto-extracted statements must be exact user text. Paraphrases remain inferences.
        if item.claim_type != "system_inference" and not any(
            item.content in str(by_id[s]["user_text"]) for s in item.source_ids
        ):
            raise ValueError("unsupported_claim")
        if item.event_time is not None:
            raise ValueError("unverified_event_time")


def save(db: Session, job: BackgroundJob, batch: ProposalBatch) -> str:
    validate_proposals(db, job, batch)
    if suppressed(db, job.owner_id, job.source_refs):
        raise ValueError("source_suppressed")
    for ordinal, proposal in enumerate(batch.memories):
        refs = [r for r in job.source_refs if r["source_id"] in proposal.source_ids]
        source_snapshot: list[dict[str, str | int]] = []
        for ref in refs:
            if ref["source_type"] == "note":
                note = db.get(Note, str(ref["source_id"]))
                # The fenced save has validated this exact source version.
                assert note is not None and note.version == ref["source_version"]
                source_snapshot.extend(dict(nested) for nested in note.source_refs)
        memory = Memory(
            owner_id=job.owner_id,
            content=proposal.content,
            claim_type=proposal.claim_type,
            source_refs=refs,
            source_snapshot=source_snapshot,
            purpose="saved_memory",
            retention_policy_id=jobs.CONFIG_VERSION,
        )
        db.add(memory)
        db.flush()
        db.add(
            MemoryCandidate(
                owner_id=job.owner_id,
                job_id=job.id,
                ordinal=ordinal,
                memory_id=memory.id,
                proposed_content=proposal.content,
                claim_type=proposal.claim_type,
                source_refs=refs,
                purpose=jobs.PURPOSE,
                retention_policy_id=jobs.CONFIG_VERSION,
                generator_version=GENERATOR,
            )
        )
        for ref in refs:
            db.add(
                ArtifactSource(
                    memory_id=memory.id,
                    owner_id=job.owner_id,
                    grant_id=str(ref["grant_ref"]),
                    grant_version=int(ref["grant_version"]),
                )
            )
    job.encrypted_config = None
    return job.id


def readable(db: Session, row: Memory) -> bool:
    for ref in row.source_refs:
        grant = db.get(ContextGrant, str(ref["grant_ref"]))
        if (
            grant is None
            or grant.owner_id != row.owner_id
            or grant.revoked_at
            or grant.deleted_at
            or grant.version != ref["grant_version"]
            or not source_available(db, grant)
        ):
            return False
        job = db.get(BackgroundJob, grant.job_id) if grant.job_id else None
        if job is None or job.experiment_config_version != jobs.CONFIG_VERSION:
            return False
    return bool(row.source_refs)


def view(db: Session, row: Memory) -> dict[str, Any]:
    valid = readable(db, row)
    return {
        **resource(row),
        "content": row.content if valid else "",
        "claim_type": row.claim_type,
        "status": row.status if valid else "needs_review",
        "event_time": row.event_time,
        "recorded_at": row.created_at,
        "scope": row.scope,
        "correction_id": row.correction_id,
        "source_available": valid,
    }


def suppress(db: Session, row: Memory, reason: str) -> None:
    for ref in [*row.source_refs, *row.source_snapshot]:
        key = source_key(ref)
        if (
            db.scalar(
                select(MemorySuppression.id).where(
                    MemorySuppression.owner_id == row.owner_id,
                    MemorySuppression.source_key == key,
                )
            )
            is None
        ):
            db.add(
                MemorySuppression(
                    owner_id=row.owner_id,
                    source_key=key,
                    reason=reason,
                    purpose="saved_memory",
                    retention_policy_id=jobs.CONFIG_VERSION,
                )
            )
    for candidate in db.scalars(select(MemoryCandidate).where(MemoryCandidate.memory_id == row.id)):
        candidate.status, candidate.proposed_content = "invalidated", ""
        bump(candidate, candidate.version)


class ExtractRequest(Input):
    source_refs: list[jobs.JobSource] = Field(min_length=1, max_length=8)


@router.post("/memory-candidates", status_code=202)
def extract(body: ExtractRequest, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    row = create_once(
        db,
        request,
        auth,
        BackgroundJob,
        body.model_dump(mode="json"),
        lambda: enqueue_sources(db, request.app.state.settings, auth.owner_id, body.source_refs),
    )
    return {"job_id": row.id, "status": row.status}


@router.get("/memory-candidates")
def candidates(db: DB, auth: Auth) -> dict[str, Any]:
    rows = db.scalars(
        select(MemoryCandidate)
        .where(MemoryCandidate.owner_id == auth.owner_id, MemoryCandidate.deleted_at.is_(None))
        .order_by(MemoryCandidate.created_at.desc())
        .limit(50)
    )
    return {"items": [candidate_view(db, row) for row in rows]}


def candidate_view(db: Session, row: MemoryCandidate) -> dict[str, Any]:
    memory = db.get(Memory, row.memory_id) if row.memory_id else None
    valid = memory is not None and not memory.deleted_at and readable(db, memory)
    return {
        **resource(row),
        "job_id": row.job_id,
        "memory_id": row.memory_id,
        "proposed_content": row.proposed_content if valid else "",
        "claim_type": row.claim_type,
        "status": row.status if valid else "invalidated",
        "generator_version": row.generator_version,
    }


@router.get("/memory-candidates/{candidate_id}")
def candidate(candidate_id: str, db: DB, auth: Auth) -> dict[str, Any]:
    return candidate_view(db, owned(db, MemoryCandidate, candidate_id, auth.owner_id))


@router.get("/memories")
def memories(
    db: DB,
    auth: Auth,
    status: Literal["active", "needs_review", "stopped"] = "active",
    q: str = Query(default="", max_length=120),
    cursor: str | None = None,
) -> dict[str, Any]:
    query = select(Memory).where(Memory.owner_id == auth.owner_id, Memory.deleted_at.is_(None))
    if cursor:
        anchor = owned(db, Memory, cursor, auth.owner_id)
        query = query.where(Memory.created_at < anchor.created_at)
    rows = list(db.scalars(query.order_by(Memory.created_at.desc()).limit(100)))
    values = [view(db, row) for row in rows]
    return {
        "items": [
            v for v in values if v["status"] == status and q.casefold() in v["content"].casefold()
        ],
        "next_cursor": rows[-1].id if len(rows) == 100 else None,
    }


@router.get("/memories/{memory_id}")
def get_memory(memory_id: str, db: DB, auth: Auth) -> dict[str, Any]:
    return view(db, owned(db, Memory, memory_id, auth.owner_id))


class Correction(Version):
    content: str | None = Field(default=None, min_length=1, max_length=1200)
    status: Literal["stopped"] | None = None


@router.patch("/memories/{memory_id}")
def correct(
    memory_id: str, body: Correction, request: Request, db: DB, auth: Auth
) -> dict[str, Any]:
    row = owned(db, Memory, memory_id, auth.owner_id)
    if not body.content and body.status is None:
        raise APIError(422, "empty_correction")
    if body.content is not None and not body.content.strip():
        raise APIError(422, "empty_correction")
    if not mutation_receipt(db, request, auth.owner_id, row, body.model_dump(mode="json")):
        if not readable(db, row):
            raise APIError(409, "source_unavailable")
        bump(row, body.expected_version)
        suppress(db, row, "correction" if body.content else "stopped")
        if body.content is not None:
            row.content, row.claim_type, row.correction_id = (
                body.content,
                "user_statement",
                str(uuid4()),
            )
        if body.status:
            row.status = body.status
    return view(db, row)


@router.get("/memories/{memory_id}/deletion-preview")
def preview(memory_id: str, db: DB, auth: Auth) -> dict[str, Any]:
    row = owned(db, Memory, memory_id, auth.owner_id)
    return {
        "memory_id": row.id,
        "version": row.version,
        "source_refs": row.source_refs,
        "scope": "memory_and_candidates_and_source_reextraction",
        "delete_original": False,
    }


class Forget(Version):
    confirmed: Literal[True]


@router.delete("/memories/{memory_id}")
def forget(memory_id: str, body: Forget, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    from app.deletion import cleanup

    def build() -> DeletionJob:
        row = owned(db, Memory, memory_id, auth.owner_id)
        bump(row, body.expected_version)
        suppress(db, row, "forgotten")
        row.status, row.deleted_at = "deleted", now()
        return DeletionJob(
            owner_id=auth.owner_id,
            target=row.id,
            target_type="memory",
            scope=["memory", "candidates", "source_suppression"],
            status="online_blocked",
            completed_steps=["online_blocked"],
        )

    job = create_once(db, request, auth, DeletionJob, body.model_dump(mode="json"), build)
    job_id, owner = job.id, auth.owner_id
    db.commit()
    return cleanup(request, job_id, owner)


def purge_unavailable(db: Session, owner: str) -> None:
    for row in db.scalars(select(Memory).where(Memory.owner_id == owner)):
        if row.deleted_at or not readable(db, row):
            row.content = ""
            if not row.deleted_at:
                row.status = "needs_review"
            for candidate in db.scalars(
                select(MemoryCandidate).where(MemoryCandidate.memory_id == row.id)
            ):
                candidate.proposed_content, candidate.status = "", "deleted"
                candidate.deleted_at = now()
