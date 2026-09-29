"""Transaction-local bulk reads; never reuse authorization data across transactions."""

from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import ContextGrant, Conversation, Message, ModelCall, Run, RunBranch, RunExecution


class RunReads:
    def __init__(self, db: Session, runs: Sequence[Run], *, details: bool = False) -> None:
        ids = [run.id for run in runs]
        self.executions = {
            row.run_id: row
            for row in db.scalars(select(RunExecution).where(RunExecution.run_id.in_(ids)))
        }
        self.messages: dict[str, list[Message]] = {rid: [] for rid in ids}
        for message in db.scalars(select(Message).where(Message.run_id.in_(ids))):
            self.messages[message.run_id].append(message)
        references = {gid for ex in self.executions.values() for gid in ex.grant_ids}
        self.grants = {
            row.id: row
            for row in db.scalars(
                select(ContextGrant).where(
                    or_(ContextGrant.run_id.in_(ids), ContextGrant.id.in_(references))
                )
            )
        }
        self.grant_ids: dict[str, list[str]] = {rid: [] for rid in ids}
        for grant in self.grants.values():
            if grant.run_id in self.grant_ids:
                self.grant_ids[grant.run_id].append(grant.id)
        source_ids = {run.session_id for run in runs} | {
            grant.source_id for grant in self.grants.values()
        }
        self.sources = {
            row.id: row
            for row in db.scalars(select(Conversation).where(Conversation.id.in_(source_ids)))
        }
        self.calls: dict[str, list[ModelCall]] = {rid: [] for rid in ids}
        self.branches: dict[str, RunBranch] = {}
        self.superseded: set[str] = set()
        if details:
            for call in db.scalars(
                select(ModelCall).where(
                    ModelCall.run_id.in_(ids), ModelCall.receipt["role"].astext == "support"
                )
            ):
                self.calls[call.run_id].append(call)
            for edge in db.scalars(
                select(RunBranch).where(
                    or_(RunBranch.run_id.in_(ids), RunBranch.parent_run_id.in_(ids))
                )
            ):
                self.branches[edge.run_id] = edge
                self.superseded.add(edge.parent_run_id)
