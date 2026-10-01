"""Explicit synthetic consumer on the existing standalone Worker entry point."""

import asyncio
import json
from collections.abc import Callable
from typing import Literal
from uuid import uuid4

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langsmith import tracing_context
from pydantic import Field, ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import jobs
from app.config import Settings, load_settings
from app.contracts import Input
from app.database import make_engine
from app.models import BackgroundJob, Idempotency
from app.records import dto, source_model
from app.security import digest

Phase = Literal["after_claim", "before_commit", "after_commit"]


class ProbeCandidate(Input):
    probe: Literal["recovery-probe/1"]
    source_count: int = Field(ge=1, le=8, strict=True)


def commit_probe(db: Session, job: BackgroundJob) -> str:
    """One content-free test side effect through the existing idempotency receipt table."""
    key = "job-probe:" + job.id
    request_hash = digest(job.id)
    previous = db.get(Idempotency, (job.owner_id, key))
    if previous is None:
        db.add(
            Idempotency(
                owner_id=job.owner_id,
                key=key,
                request_hash=request_hash,
                resource_type="job_probe",
                resource_id=job.id,
            )
        )
    elif (
        previous.resource_type != "job_probe"
        or previous.resource_id != job.id
        or previous.request_hash != request_hash
    ):
        raise ValueError("idempotency_conflict")
    return job.id


async def execute(
    engine: Engine,
    lease: jobs.Lease,
    *,
    phase: Callable[[Phase], None] | None = None,
    model: FakeMessagesListChatModel | None = None,
) -> None:
    with Session(engine) as db, db.begin():
        job = jobs.fenced(db, lease)
        if job is None:
            return
        sources = []
        for ref in job.source_refs:
            row = db.get(source_model(str(ref["source_type"])), str(ref["source_id"]))
            assert row is not None
            # The probe reads actual authorized records, but persists no candidate text.
            sources.append(dto(db, row))
        remaining = (job.deadline_at - jobs.clock(db)).total_seconds()
    encoded = json.dumps(sources, default=str, ensure_ascii=False)
    request_id = jobs.reserve(engine, lease, len(encoded.encode("utf-8")) + 32)
    if request_id is None:
        return
    if not jobs.renew(engine, lease):
        return
    adapter = model or FakeMessagesListChatModel(
        cache=False,
        responses=[
            AIMessage(
                content=json.dumps({"probe": "recovery-probe/1", "source_count": len(sources)}),
                usage_metadata={"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
            )
        ],
    )
    pending: asyncio.Task[AIMessage] | None = None
    try:
        with tracing_context(enabled=False):
            async with asyncio.timeout(max(0.001, remaining)):
                pending = asyncio.create_task(
                    adapter.ainvoke([HumanMessage(encoded)], config={"callbacks": []})
                )
                while not pending.done():
                    await asyncio.wait({pending}, timeout=0.1)
                    if not jobs.renew(engine, lease):
                        pending.cancel()
                        return
                response = await pending
                if not isinstance(response.content, str):
                    raise ValueError("schema")
                candidate = ProbeCandidate.model_validate_json(response.content)
                if candidate.source_count != len(sources):
                    raise ValueError("schema")
                usage = response.usage_metadata
                actual = usage["total_tokens"] if usage else None
                if usage and (
                    usage["input_tokens"] < 0
                    or usage["output_tokens"] < 0
                    or usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]
                ):
                    raise ValueError("schema")
                if phase:
                    phase("before_commit")
                committed = jobs.complete(engine, lease, request_id, actual, commit_probe)
                if committed and phase:
                    phase("after_commit")
    except TimeoutError:
        jobs.fail(engine, lease, "timeout")
    except (ValueError, ValidationError):
        jobs.fail(engine, lease, "schema")
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


def execute_one(
    engine: Engine,
    settings: Settings,
    worker_id: str,
    *,
    phase: Callable[[Phase], None] | None = None,
) -> bool:
    jobs.require_probe(settings)
    lease = jobs.claim(engine, worker_id)
    if lease is None:
        return False
    if phase:
        phase("after_claim")
    try:
        asyncio.run(execute(engine, lease, phase=phase))
    except DBAPIError:
        # Unknown commit outcome: never replay a mutation in this process. On restart,
        # succeeded + Idempotency are checked before a lease can be reclaimed.
        raise
    except Exception:
        jobs.fail(engine, lease, "execution_error")
    return True


async def consume(stop: asyncio.Event, *, once: bool = False, pause: Phase | None = None) -> None:
    settings = load_settings()
    jobs.require_probe(settings)
    assert settings.database_url is not None
    engine = make_engine(settings.database_url.get_secret_value())
    worker_id = str(uuid4())
    failures = 0

    def phase(value: Phase) -> None:
        if value == pause:
            print("job.probe_pause phase=" + value, flush=True)
            # Fault injection exists only behind the isolated test/fake gate.
            import threading

            threading.Event().wait()

    print("worker.started consumers=1 mode=job-probe", flush=True)
    try:
        while not stop.is_set():
            try:
                active = asyncio.create_task(
                    asyncio.to_thread(execute_one, engine, settings, worker_id, phase=phase)
                )
                try:
                    await asyncio.shield(active)
                except asyncio.CancelledError:
                    # Drain the bounded in-flight operation before disposing its pool.
                    await active
                    raise
                failures = 0
            except DBAPIError:
                failures += 1
                print("job.database_unavailable attempt=" + str(failures), flush=True)
                if failures >= 3:
                    raise RuntimeError("job_database_unavailable") from None
            if once:
                return
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=jobs.delay(failures) if failures else 0.1
                )
            except TimeoutError:
                pass
    finally:
        engine.dispose()
        print("worker.stopped consumers=1 mode=job-probe", flush=True)
