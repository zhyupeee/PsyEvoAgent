"""Explicit live S2-STEP04 acceptance on an isolated synthetic test database only."""

import argparse
import asyncio
import json
import os
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import jobs, memory_worker
from app.config import Settings, load_settings
from app.database import make_engine
from app.memory import enqueue_sources
from app.memory_models import MemoryCandidate
from app.models import BackgroundJob, JobBudget, Note, User, now
from app.provider_config import read_config
from app.security import digest

FIXTURE = "我喜欢在晚饭后散步十分钟。今天我有些紧张。"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-file", type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    settings = load_settings()
    if (
        settings.environment != "test"
        or settings.database_url is None
        or os.environ.get("CI")
        or os.environ.get("PSYEVO_CHECK_NETWORK")
    ):
        raise SystemExit("Live memory acceptance requires explicit isolated test configuration")
    if args.config_file:
        settings = read_config(args.config_file, settings)
    settings = Settings.model_validate(
        {**settings.model_dump(), "support_mode": "live", "memory_mode": "live"}
    )
    assert settings.database_url is not None
    engine = make_engine(settings.database_url.get_secret_value())
    receipt: dict[str, object] = {
        "step_id": "S2-STEP04.4",
        "execution_kind": "live",
        "started": now().isoformat(),
        "fixture": FIXTURE,
        "fixture_hash": digest(FIXTURE),
        "schema": "memory-proposal/1",
        "versions": {
            name: version(name)
            for name in ("langmem", "trustcall", "langchain-core", "langchain-openai", "langgraph")
        },
        "model": settings.provider_model,
        "provider": settings.provider_base_url,
        "expected": "LangMem candidates validated and committed once through PG",
        "passed": False,
        "limitations": [
            "Synthetic sources only",
            "Price/retention/region unknown",
            "No summary/retrieval/clinical validation",
            "Fault injection receipts are separate",
        ],
    }
    try:
        with Session(engine) as db, db.begin():
            user = User(email=uuid4().hex + "@example.com", password_hash="synthetic-no-login")
            db.add(user)
            db.flush()
            note = Note(owner_id=user.id, kind="free", title="", body=FIXTURE, status="saved")
            db.add(note)
            db.flush()
            job = enqueue_sources(
                db,
                settings,
                user.id,
                [
                    jobs.JobSource(
                        source_type="note", source_id=note.id, source_version=note.version
                    )
                ],
            )
            jid, owner, source_id = job.id, user.id, note.id
            receipt.update(job_id=jid, source_refs=job.source_refs)
        lease = jobs.claim(engine, str(uuid4()), kind="memory_extraction")
        if lease is None or lease.job_id != jid:
            raise ValueError("other_work_pending")
        asyncio.run(memory_worker.execute(engine, settings, lease))
        with Session(engine) as db:
            stored_job = db.get(BackgroundJob, jid)
            assert stored_job
            job = stored_job
            budget = db.get(JobBudget, job.budget_ref)
            assert budget
            candidates = list(
                db.scalars(select(MemoryCandidate).where(MemoryCandidate.job_id == jid))
            )
            receipt.update(
                status=job.status,
                error_code=job.error_code,
                budget_ref=budget.id,
                calls=budget.calls,
                candidates=[
                    {
                        "id": c.id,
                        "memory_id": c.memory_id,
                        "content": c.proposed_content,
                        "claim_type": c.claim_type,
                        "source_refs": c.source_refs,
                    }
                    for c in candidates
                ],
            )
            receipt["passed"] = job.status == "succeeded" and len(candidates) > 0
        with Session(engine) as db, db.begin():
            repeated = enqueue_sources(
                db,
                settings,
                owner,
                [
                    jobs.JobSource(
                        source_type="note",
                        source_id=source_id,
                        source_version=1,
                    )
                ],
            )
            receipt["duplicate_job_id"] = repeated.id
            assert repeated.id == jid
    except Exception as error:
        receipt["passed"] = False
        receipt["error_type"] = type(error).__name__
    finally:
        receipt["ended"] = now().isoformat()
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        engine.dispose()
    print("memory.live passed=" + str(receipt["passed"]))
    if not receipt["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
