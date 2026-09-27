"""STEP07 owner-scoped history, revision edges and voluntary feedback."""

from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field, field_validator
from sqlalchemy import Select, select, tuple_
from sqlalchemy.orm import Session

from app.api import DB, APIError, Auth, create_once, owned, resource
from app.contracts import Input, Version
from app.models import ContextGrant, Conversation, Feedback, Message, Run, RunBranch
from app.runs import TERMINAL, RunInput, execution, snapshot, sources_available

router = APIRouter(prefix="/api/v1")


def superseded_runs() -> Select[tuple[str]]:
    return select(RunBranch.parent_run_id)


def last_input(db: Session, session_id: str) -> Message | None:
    return db.scalar(
        select(Message)
        .join(Run, Run.id == Message.run_id)
        .where(
            Run.session_id == session_id,
            Run.deleted_at.is_(None),
            Run.id.not_in(superseded_runs()),
            Message.role == "user",
            Message.deleted_at.is_(None),
        )
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(1)
    )


def fork_run(
    db: Session, source: Conversation, message_id: str, version: int, content: str | None, kind: str
) -> Run:
    message = owned(db, Message, message_id, source.owner_id)
    parent = owned(db, Run, message.run_id, source.owner_id)
    latest = last_input(db, source.id)
    if (
        source.status != "active"
        or parent.session_id != source.id
        or message.role != "user"
        or message.version != version
        or latest is None
        or latest.id != message.id
        or db.scalar(
            select(Run.id).where(
                Run.session_id == source.id, Run.deleted_at.is_(None), Run.status.not_in(TERMINAL)
            )
        )
    ):
        raise APIError(409, "revision_conflict")
    if not sources_available(db, parent, execution(db, parent)):
        raise APIError(404, "not_found")
    run = Run(
        owner_id=source.owner_id, session_id=source.id, session_version=source.version, kind=kind
    )
    db.add(run)
    db.flush()
    parent_execution = execution(db, parent)
    if parent_execution:
        for grant_id in parent_execution.grant_ids:
            grant = owned(db, ContextGrant, grant_id, source.owner_id)
            db.add(
                ContextGrant(
                    owner_id=source.owner_id,
                    run_id=run.id,
                    source_id=grant.source_id,
                    source_version=grant.source_version,
                    purpose="current_run",
                )
            )
    db.add_all(
        [
            RunBranch(owner_id=source.owner_id, run_id=run.id, parent_run_id=parent.id, kind=kind),
            Message(
                owner_id=source.owner_id,
                run_id=run.id,
                role="user",
                content=message.content if content is None else content,
                version=message.version + 1,
                source_refs=[{"source_id": message.id, "version": message.version}],
            ),
        ]
    )
    db.flush()
    return run


def turn(db: Session, run: Run) -> dict[str, Any]:
    result = snapshot(db, run)
    message = db.scalar(
        select(Message).where(
            Message.run_id == run.id, Message.role == "user", Message.deleted_at.is_(None)
        )
    )
    edge = db.scalar(select(RunBranch).where(RunBranch.run_id == run.id))
    return {
        **result,
        "input_text": message.content if message else None,
        "input_id": message.id if message else None,
        "input_version": message.version if message else None,
        "branch_id": run.id,
        "parent_run_id": edge.parent_run_id if edge else None,
        "is_current": db.scalar(select(RunBranch.id).where(RunBranch.parent_run_id == run.id))
        is None,
    }


@router.get("/sessions")
def sessions(
    db: DB,
    auth: Auth,
    q: str = Query(default="", max_length=120),
    status: Literal["active", "archived"] = "active",
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    query = select(Conversation).where(
        Conversation.owner_id == auth.owner_id,
        Conversation.deleted_at.is_(None),
        Conversation.status == status,
    )
    if q.strip():
        query = query.where(Conversation.title.icontains(q.strip(), autoescape=True))
    if cursor:
        anchor = db.scalar(query.where(Conversation.id == cursor))
        if anchor is None:
            raise APIError(422, "invalid_cursor")
        query = query.where(
            tuple_(Conversation.created_at, Conversation.id) < (anchor.created_at, anchor.id)
        )
    rows = db.scalars(
        query.order_by(Conversation.created_at.desc(), Conversation.id.desc()).limit(limit + 1)
    ).all()
    return {
        "items": [resource(row) for row in rows[:limit]],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


@router.get("/sessions/{session_id}/history")
def history(
    session_id: str,
    db: DB,
    auth: Auth,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    owned(db, Conversation, session_id, auth.owner_id)
    query = select(Run).where(
        Run.session_id == session_id, Run.owner_id == auth.owner_id, Run.deleted_at.is_(None)
    )
    if cursor:
        anchor = db.scalar(query.where(Run.id == cursor))
        if anchor is None:
            raise APIError(422, "invalid_cursor")
        query = query.where(tuple_(Run.created_at, Run.id) < (anchor.created_at, anchor.id))
    rows = db.scalars(query.order_by(Run.created_at.desc(), Run.id.desc()).limit(limit + 1)).all()
    # Unavailable grants never return either input or output in history.
    return {
        "items": [
            turn(db, row) for row in rows[:limit] if sources_available(db, row, execution(db, row))
        ],
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


class Revision(Version):
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def nonblank(cls, value: str) -> str:
        RunInput(message=value)
        return value


@router.post("/sessions/{session_id}/messages/{message_id}/revisions", status_code=201)
def revise(
    session_id: str, message_id: str, body: Revision, request: Request, db: DB, auth: Auth
) -> dict[str, Any]:
    # Share input validation with the existing start boundary.
    content = body.content
    source = owned(db, Conversation, session_id, auth.owner_id)
    run = create_once(
        db,
        request,
        auth,
        Run,
        body.model_dump(),
        lambda: fork_run(db, source, message_id, body.expected_version, content, "revision"),
    )
    return turn(db, run)


class FeedbackCreate(Input):
    run_id: str = Field(min_length=1, max_length=36)
    helpfulness: Literal["helpful", "neutral", "unhelpful", "not_rated"]
    category: Literal["general", "misunderstood", "listen_only", "inappropriate"] = "general"
    comment: str | None = Field(default=None, max_length=1000, pattern=r"^[^\x00]*$")


@router.post("/feedback", status_code=201)
def feedback(body: FeedbackCreate, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    run = owned(db, Run, body.run_id, auth.owner_id)
    snapshot(db, run)
    if run.status not in TERMINAL:
        raise APIError(409, "run_active")
    row = create_once(
        db,
        request,
        auth,
        Feedback,
        body.model_dump(),
        lambda: Feedback(owner_id=auth.owner_id, **body.model_dump()),
    )
    return {"feedback_id": row.id, "status": "saved", "notice_version": row.notice_version}
