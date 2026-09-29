"""STEP07 owner-scoped history, revision edges and voluntary feedback."""

from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field, field_validator
from sqlalchemy import Select, or_, select, tuple_
from sqlalchemy.orm import Session

from app.api import DB, APIError, Auth, create_once, owned, resource
from app.contracts import Input, Version
from app.models import ContextGrant, Conversation, Feedback, Message, Run, RunBranch
from app.runs import TERMINAL, RunInput, execution, snapshot, sources_available
from app.support import (
    Budget,
    ContextTurn,
    SupportInput,
    context_size,
    history_capacity,
    select_mode,
)

router = APIRouter(prefix="/api/v1")


def superseded_runs() -> Select[tuple[str]]:
    return select(RunBranch.parent_run_id)


def main_runs(owner: str, session_id: str) -> Select[tuple[Run]]:
    return select(Run).where(
        Run.owner_id == owner,
        Run.session_id == session_id,
        Run.deleted_at.is_(None),
        Run.id.not_in(superseded_runs()),
    )


def context_history(
    db: Session, run: Run, request: SupportInput, budget: Budget
) -> tuple[ContextTurn, ...]:
    if request.versions.policy_version == "support-policy/1":
        return ()
    remaining = history_capacity(request.source.content, select_mode(request), budget)
    if remaining < 0:
        return ()
    query = main_runs(run.owner_id, run.session_id).where(
        Run.status == "completed",
        tuple_(Run.created_at, Run.id) < (run.created_at, run.id),
    )
    selected: list[ContextTurn] = []
    rows = db.scalars(
        query.order_by(Run.created_at.desc(), Run.id.desc()).execution_options(yield_per=50)
    )
    try:
        for prior in rows:
            if not sources_available(db, prior, execution(db, prior)):
                continue
            messages = db.scalars(select(Message).where(Message.run_id == prior.id)).all()
            user = next((m for m in messages if m.role == "user"), None)
            assistant = next((m for m in messages if m.role == "assistant"), None)
            if (
                user is None
                or assistant is None
                or any(
                    m.deleted_at or m.owner_id != run.owner_id or not m.content
                    for m in (user, assistant)
                )
            ):
                continue
            turn = ContextTurn(
                run_id=prior.id,
                user_id=user.id,
                user_version=user.version,
                assistant_id=assistant.id,
                assistant_version=assistant.version,
                user_text=user.content,
                assistant_text=assistant.content,
            )
            remaining -= context_size(turn)
            if remaining < 0:
                break
            selected.append(turn)
    finally:
        rows.close()
    return tuple(reversed(selected))


def context_available(db: Session, run: Run, history: tuple[ContextTurn, ...]) -> bool:
    for turn in history:
        prior = db.scalar(main_runs(run.owner_id, run.session_id).where(Run.id == turn.run_id))
        if (
            prior is None
            or prior.status != "completed"
            or (prior.created_at, prior.id) >= (run.created_at, run.id)
            or not sources_available(db, prior, execution(db, prior))
        ):
            return False
        for mid, version in (
            (turn.user_id, turn.user_version),
            (turn.assistant_id, turn.assistant_version),
        ):
            message = db.get(Message, mid)
            if (
                message is None
                or message.run_id != prior.id
                or message.version != version
                or message.deleted_at
            ):
                return False
    return True


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
        "created_at": run.created_at.isoformat(),
        "input_text": message.content if message else None,
        "input_id": message.id if message else None,
        "input_version": message.version if message else None,
        "branch_id": run.id,
        "parent_run_id": edge.parent_run_id if edge else None,
        "is_current": db.scalar(select(RunBranch.id).where(RunBranch.parent_run_id == run.id))
        is None,
    }


@router.get("/sessions/{session_id}/timeline")
def timeline(
    session_id: str,
    db: DB,
    auth: Auth,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    owned(db, Conversation, session_id, auth.owner_id)
    query = main_runs(auth.owner_id, session_id)
    if cursor:
        # A superseded anchor remains a valid position, but never supplies content.
        anchor = db.scalar(
            select(Run).where(
                Run.id == cursor,
                Run.session_id == session_id,
                Run.owner_id == auth.owner_id,
                Run.deleted_at.is_(None),
            )
        )
        if anchor is None:
            raise APIError(422, "invalid_cursor")
        query = query.where(tuple_(Run.created_at, Run.id) < (anchor.created_at, anchor.id))
    items: list[dict[str, Any]] = []
    rows = db.scalars(
        query.order_by(Run.created_at.desc(), Run.id.desc()).execution_options(yield_per=50)
    )
    try:
        for row in rows:
            if not sources_available(db, row, execution(db, row)):
                continue
            item = turn(db, row)
            if not item["input_id"]:  # An empty send draft is not a conversation turn.
                continue
            items.append(item)
            if len(items) > limit:
                break
    finally:
        rows.close()
    return {
        "items": list(reversed(items[:limit])),
        "next_cursor": items[limit - 1]["run_id"] if len(items) > limit else None,
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
        "has_pending_titles": db.scalar(
            select(Conversation.id)
            .where(
                Conversation.owner_id == auth.owner_id,
                Conversation.deleted_at.is_(None),
                Conversation.status == status,
                Conversation.title_source == "default",
                or_(
                    Conversation.title_generation_status.in_({"queued", "running"}),
                    (Conversation.title_generation_status == "not_requested")
                    & Conversation.id.in_(
                        select(Run.session_id).where(Run.status.in_({"queued", "running"}))
                    ),
                ),
            )
            .limit(1)
        )
        is not None,
        "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
    }


@router.get("/sessions/{session_id}/history")
def history(
    session_id: str,
    db: DB,
    auth: Auth,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    old_only: bool = False,
) -> dict[str, Any]:
    owned(db, Conversation, session_id, auth.owner_id)
    query = select(Run).where(
        Run.session_id == session_id, Run.owner_id == auth.owner_id, Run.deleted_at.is_(None)
    )
    if old_only:
        query = query.where(Run.id.in_(superseded_runs()))
    if cursor:
        anchor = db.scalar(query.where(Run.id == cursor))
        if anchor is None:
            raise APIError(422, "invalid_cursor")
        query = query.where(tuple_(Run.created_at, Run.id) < (anchor.created_at, anchor.id))
    if old_only:
        items = []
        old_rows = db.scalars(
            query.order_by(Run.created_at.desc(), Run.id.desc()).execution_options(yield_per=50)
        )
        try:
            for row in old_rows:
                if sources_available(db, row, execution(db, row)):
                    items.append(turn(db, row))
                    if len(items) > limit:
                        break
        finally:
            old_rows.close()
        return {
            "items": items[:limit],
            "next_cursor": items[limit - 1]["run_id"] if len(items) > limit else None,
        }
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
