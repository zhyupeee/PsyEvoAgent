"""Standalone, bounded fake execution using the existing single Support graph."""

import asyncio
import json
from dataclasses import asdict
from decimal import Decimal
from uuid import UUID

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Message, ModelCall, Run, now
from app.runs import emit, executable, execution, lock_owner, terminal
from app.support import (
    Budget,
    CallReceipt,
    ModelProfile,
    Source,
    SupportInput,
    SupportRuntime,
    VersionBinding,
)


def fake_model() -> FakeMessagesListChatModel:
    return FakeMessagesListChatModel(
        cache=False,
        responses=[
            AIMessage(
                content=json.dumps({"text": "这是隔离合成测试回应。"}, ensure_ascii=False),
                usage_metadata={"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
            )
        ],
    )


def claim(engine: Engine) -> tuple[str, str] | None:
    # Do not lock run before owner: all writes use the same lock ordering as identity.
    with Session(engine) as db:
        candidates = db.execute(
            select(Run.id, Run.owner_id)
            .where(Run.status.in_({"queued", "running"}))
            .order_by(Run.created_at)
            .limit(100)
        ).all()
    for run_id, owner in candidates:
        with Session(engine) as db, db.begin():
            lock_owner(db, owner)
            run = db.get(Run, run_id)
            assert run is not None
            ex = execution(db, run)
            if ex is None or run.status not in {"queued", "running"}:
                continue
            if ex.deadline_at <= now():
                terminal(
                    db,
                    run,
                    ex,
                    "interrupted" if run.status == "running" else "failed",
                    "interrupted" if run.status == "running" else "deadline",
                )
                continue
            if run.status == "running":
                continue
            run.status, run.version, run.updated_at = "running", run.version + 1, now()
            if not executable(db, run, ex):
                terminal(db, run, ex, "cancelled", "source_unavailable")
                continue
            emit(db, run, ex, "run.started", {})
            return run_id, owner
    return None


def allowed(engine: Engine, run_id: str, owner: str, generation: int) -> bool:
    with Session(engine) as db, db.begin():
        lock_owner(db, owner)
        run = db.get(Run, run_id)
        if run is None:
            return False
        ex = execution(db, run)
        return ex is not None and ex.generation == generation and executable(db, run, ex)


def store_call(engine: Engine, receipt: CallReceipt) -> None:
    # Explicit metadata DTO; no prompt, response, exception text or credentials.
    payload = {
        key: str(value) if isinstance(value, Decimal) else value
        for key, value in asdict(receipt).items()
    }
    with Session(engine) as db, db.begin():
        db.execute(
            insert(ModelCall)
            .values(request_id=receipt.request_id, run_id=receipt.run_id, receipt=payload)
            .on_conflict_do_update(index_elements=[ModelCall.request_id], set_={"receipt": payload})
        )


async def execute(
    engine: Engine, run_id: str, owner: str, model: FakeMessagesListChatModel | None = None
) -> None:
    # This coroutine runs in a bounded worker thread, never in the HTTP event loop.
    with Session(engine) as db:
        run = db.get(Run, run_id)
        assert run is not None
        ex = execution(db, run)
        message = db.scalar(select(Message).where(Message.run_id == run_id, Message.role == "user"))
        assert ex is not None and message is not None
        generation = ex.generation
        remaining = (ex.deadline_at - now()).total_seconds()
        bound_budget = Budget.model_validate(ex.budget)
        request = SupportInput(
            owner_id=UUID(owner),
            session_id=UUID(run.session_id),
            run_id=UUID(run_id),
            synthetic=True,
            preference="explore" if ex.preference == "explore" else "listen",
            versions=VersionBinding.model_validate(ex.versions),
            source=Source(
                owner_id=UUID(owner),
                session_id=UUID(run.session_id),
                message_id=UUID(message.id),
                message_version=message.version,
                content=message.content,
            ),
        )
    if remaining <= 0:
        with Session(engine) as db, db.begin():
            lock_owner(db, owner)
            run = db.get(Run, run_id)
            assert run is not None
            terminal(db, run, execution(db, run), "interrupted", "interrupted")
        return
    runtime = SupportRuntime(
        model or fake_model(),
        profile=ModelProfile(),
        authorize=lambda _: allowed(engine, run_id, owner, generation),
        record_call=lambda receipt: store_call(engine, receipt),
    )
    task = asyncio.create_task(
        runtime.run(
            request,
            bound_budget.model_copy(
                update={"deadline_seconds": min(bound_budget.deadline_seconds, remaining)}
            ),
        )
    )
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=0.05)
            if not done and not allowed(engine, run_id, owner, generation):
                task.cancel()
        result = await task
        with Session(engine) as db, db.begin():
            lock_owner(db, owner)
            run = db.get(Run, run_id)
            assert run is not None
            ex = execution(db, run)
            assert ex is not None
            if run.status != "running" or ex.generation != generation:
                return
            if ex.deadline_at <= now():
                terminal(db, run, ex, "interrupted", "interrupted")
            elif not executable(db, run, ex):
                terminal(db, run, ex, "cancelled", "source_unavailable")
            elif result.rule_verdict != "pass" or result.text is None:
                terminal(db, run, ex, "failed", result.stop_reason or "output_unavailable")
            else:
                # Only a checked complete candidate enters the public event transaction.
                emit(db, run, ex, "message.delta", {"text": result.text})
                db.add(
                    Message(owner_id=owner, run_id=run_id, role="assistant", content=result.text)
                )
                terminal(db, run, ex, "completed", None)
    finally:
        if not task.done():
            task.cancel()
            await task


def execute_one(engine: Engine) -> bool:
    selected = claim(engine)
    if selected is None:
        return False
    run_id, owner = selected
    try:
        asyncio.run(execute(engine, run_id, owner))
    except Exception:
        with Session(engine) as db, db.begin():
            lock_owner(db, owner)
            run = db.get(Run, run_id)
            assert run is not None
            terminal(db, run, execution(db, run), "failed", "execution_error")
    return True


async def consume(stop: asyncio.Event) -> None:
    from app.config import load_settings
    from app.database import make_engine

    settings = load_settings()
    if settings.support_mode != "fake" or settings.database_url is None:
        raise ValueError("Support worker requires explicitly enabled isolated fake mode")
    engine = make_engine(settings.database_url.get_secret_value())
    print("worker.started consumers=1 mode=fake", flush=True)
    try:
        while not stop.is_set():
            active = asyncio.create_task(asyncio.to_thread(execute_one, engine))
            try:
                await asyncio.shield(active)
            except asyncio.CancelledError:
                # A thread cannot be killed safely. Drain the original bounded run
                # before disposing its pool; never schedule another claim on shutdown.
                await active
                raise
            try:
                await asyncio.wait_for(stop.wait(), timeout=0.1)
            except TimeoutError:
                pass
    finally:
        engine.dispose()
        print("worker.stopped consumers=1 mode=fake", flush=True)
