"""STEP06 read models; no history management or exercise persistence."""

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import case, select

from app.api import DB, Auth, owned
from app.history import superseded_runs, turn
from app.models import Conversation, Message, Run

router = APIRouter(prefix="/api/v1")


@router.get("/sessions/{session_id}/current-run")
def current_run(session_id: str, db: DB, auth: Auth) -> dict[str, Any] | None:
    owned(db, Conversation, session_id, auth.owner_id)
    run = db.scalar(
        select(Run)
        .where(
            Run.session_id == session_id,
            Run.owner_id == auth.owner_id,
            Run.deleted_at.is_(None),
            Run.id.not_in(superseded_runs()),
        )
        # An unsent draft in another tab must not hide the run that can be stopped.
        .order_by(
            case(
                (Run.status.in_({"queued", "running"}), 0),
                (
                    select(Message.id)
                    .where(
                        Message.run_id == Run.id,
                        Message.role == "user",
                        Message.deleted_at.is_(None),
                    )
                    .exists(),
                    1,
                ),
                else_=2,
            ),
            Run.created_at.desc(),
            Run.id.desc(),
        )
        .limit(1)
    )
    if run is None:
        return None
    return turn(db, run)


@router.get("/resources/exercises/attention")
def exercise(request: Request, auth: Auth) -> dict[str, Any]:
    # Content review is external and unresolved. Never expose this fixture in development.
    synthetic = request.app.state.settings.environment == "test"
    return {
        "id": "attention",
        "title": "注意身边的事物",
        "version": "synthetic-attention/1",
        "review_status": "unreviewed",
        "available": synthetic,
        "steps": [
            "看看身边，留意一件你能看见的东西。",
            "如果愿意，留意此刻听到的一种声音。",
            "留意身体与椅子或地面的接触。也可以直接跳过。",
        ]
        if synthetic
        else [],
    }


@router.get("/resources/support")
def support(auth: Auth) -> dict[str, Any]:
    return {
        "items": [],
        "checked_at": None,
        "message": (
            "暂无已核实的校内值班信息。可从学校官方网站查找学生事务或"
            "心理支持部门的公开入口，并核对信息日期。"
        ),
    }
