"""Memory consumer of the original PG jobs/Worker, never a second Agent."""

import asyncio
import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, BaseMessage
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import jobs
from app.config import Settings, load_settings
from app.database import make_engine
from app.job_worker import Phase
from app.memory import ProposalBatch, save, source_payload
from app.memory_extractor import Invoke, extract
from app.provider import open_provider
from app.support import ProviderFailure


async def execute(
    engine: Engine,
    settings: Settings,
    lease: jobs.Lease,
    *,
    invoke: Invoke | None = None,
    phase: Callable[[Phase], None] | None = None,
) -> None:
    with Session(engine) as db, db.begin():
        job = jobs.fenced(db, lease)
        if job is None:
            return
        if job.provider_profile.get("mode") != settings.memory_mode:
            jobs.finish(job, "invalidated", "configuration_changed", jobs.clock(db))
            return
        payload = source_payload(db, job.source_refs)
        remaining = (job.deadline_at - jobs.clock(db)).total_seconds()
        selected = settings
        if settings.memory_mode == "live":
            from app.provider_settings import decrypt

            if job.encrypted_config:
                selected = Settings.model_validate(
                    {
                        **settings.model_dump(),
                        **decrypt(settings, job.owner_id, job.id, job.encrypted_config),
                    }
                )
            elif (
                job.provider_profile.get("model") != settings.provider_model
                or job.provider_profile.get("base_url") != settings.provider_base_url
            ):
                jobs.finish(job, "invalidated", "configuration_changed", jobs.clock(db))
                return
    request_id: str | None = None
    actual: int | None = None

    async def call(messages: list[BaseMessage]) -> AIMessage:
        nonlocal request_id, actual
        # UTF-8 bytes are a conservative input token bound, including LangMem/schema prompts.
        reserved = sum(len(str(m.content).encode("utf-8")) for m in messages) + 1024 + 256
        request_id = jobs.reserve(engine, lease, reserved, live=settings.memory_mode == "live")
        if request_id is None or not jobs.renew(engine, lease):
            raise ValueError("call_not_authorized")
        if invoke is not None:
            if settings.memory_mode != "fake" or settings.environment != "test":
                raise ValueError("injection_requires_fake")
            response = await invoke(messages)
        elif settings.memory_mode == "live":
            async with open_provider(
                selected.model_copy(update={"provider_max_output_tokens": 1024})
            ) as provider:
                response = await provider.ainvoke(messages, config={"callbacks": []})
        else:
            if settings.environment != "test" or settings.memory_mode != "fake":
                raise ValueError("fake_requires_test")
            text = str(payload[0]["user_text"]).strip().split("\n")[0][:500]
            data: dict[str, Any] = {
                "memories": [
                    {
                        "content": text,
                        "claim_type": "user_statement",
                        "source_ids": [payload[0]["source_id"]],
                        "evidence": text,
                        "event_time": None,
                    }
                ]
                if text
                else []
            }
            response = AIMessage(
                content=json.dumps(data, ensure_ascii=False),
                usage_metadata={"input_tokens": 10, "output_tokens": 10, "total_tokens": 20},
            )
        usage = response.usage_metadata
        if usage is not None:
            if (
                any(
                    type(value) is not int or value < 0
                    for value in (
                        usage["input_tokens"],
                        usage["output_tokens"],
                        usage["total_tokens"],
                    )
                )
                or usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]
                or usage["total_tokens"] > reserved
            ):
                raise ValueError("invalid_usage")
            actual = usage["total_tokens"]
        return response

    pending: asyncio.Task[ProposalBatch] | None = None
    try:
        async with asyncio.timeout(max(0.001, remaining)):
            pending = asyncio.create_task(extract(payload, call))
            while not pending.done():
                await asyncio.wait({pending}, timeout=0.2)
                if not jobs.renew(engine, lease):
                    pending.cancel()
                    return
            batch = await pending
            assert request_id is not None
            if phase:
                phase("before_commit")
            if (
                jobs.complete(
                    engine, lease, request_id, actual, lambda db, job: save(db, job, batch)
                )
                and phase
            ):
                phase("after_commit")
    except TimeoutError:
        jobs.fail(engine, lease, "timeout")
    except ProviderFailure as error:
        jobs.fail(engine, lease, "temporary_io" if error.kind == "transient" else "schema")
    except ValueError:
        jobs.fail(engine, lease, "schema")
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


def execute_one(
    engine: Engine, settings: Settings, *, phase: Callable[[Phase], None] | None = None
) -> bool:
    if settings.memory_mode == "disabled":
        return False
    lease = jobs.claim(engine, str(uuid4()), kind="memory_extraction")
    if lease is None:
        return False
    if phase:
        phase("after_claim")
    try:
        asyncio.run(execute(engine, settings, lease, phase=phase))
    except DBAPIError:
        raise
    except Exception:
        jobs.fail(engine, lease, "schema")
    return True


async def consume(stop: asyncio.Event, *, once: bool = False, pause: Phase | None = None) -> None:
    settings = load_settings()
    if settings.memory_mode == "disabled" or settings.database_url is None:
        raise ValueError("memory_not_enabled")
    if pause and (settings.environment != "test" or settings.memory_mode != "fake"):
        raise ValueError("pause_requires_test_fake")
    engine = make_engine(settings.database_url.get_secret_value())
    failures = 0

    def phase(value: Phase) -> None:
        if pause == value:
            import threading

            print("memory.probe_pause phase=" + value, flush=True)
            threading.Event().wait()

    try:
        while not stop.is_set():
            try:
                task = asyncio.create_task(
                    asyncio.to_thread(execute_one, engine, settings, phase=phase)
                )
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
                failures = 0
            except DBAPIError:
                failures += 1
                if failures >= 3:
                    raise RuntimeError("memory_database_unavailable") from None
            if once:
                return
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=jobs.delay(failures) if failures else 0.2
                )
            except TimeoutError:
                pass
    finally:
        engine.dispose()
