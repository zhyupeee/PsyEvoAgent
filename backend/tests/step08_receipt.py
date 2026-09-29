"""Direct post-restart verification for actual live browser runs; metadata only."""

import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_settings
from app.database import make_engine
from app.deletion import receipt
from app.models import DeletionJob, Message, ModelCall, Run, RunEvent


def main() -> None:
    browser = json.loads(Path(sys.argv[1]).read_text())
    settings = load_settings()
    assert settings.database_url is not None
    engine = make_engine(settings.database_url.get_secret_value())
    facts: dict[str, object] = {}
    with Session(engine) as db:
        for name, status in (("run_id", "completed"), ("cancelled_run_id", "cancelled")):
            run = db.get(Run, browser[name])
            assert run is not None and run.status == status and run.deleted_at
            calls = db.scalars(select(ModelCall).where(ModelCall.run_id == run.id)).all()
            assert len(calls) == 1
            call = calls[0].receipt
            assert call["model_ref"] == "grok-4.7" and call["actual_cost"] is None
            assert call["reserved_cost"] is None and call["currency"] == "unknown"
            if status == "completed":
                tokens = call["actual_tokens"]
                assert call["status"] == "settled" and isinstance(tokens, int) and tokens > 0
            else:
                assert call["status"] == "cancelled" and call["actual_tokens"] is None
            assert not db.scalars(select(RunEvent).where(RunEvent.run_id == run.id)).all()
            assert all(
                m.deleted_at and m.content == ""
                for m in db.scalars(select(Message).where(Message.run_id == run.id))
            )
            facts[name] = {"run_id": run.id, "status": run.status, "ledger": call}
        job = db.scalar(select(DeletionJob).where(DeletionJob.target == browser["session_id"]))
        assert job is not None and job.status == "completed"
        result = receipt(job, db)
        assert result["external_provider_status"] == "unknown"
        assert "external_provider" not in result["not_applicable"]
        facts["deletion"] = result
    engine.dispose()
    Path(sys.argv[2]).write_text(json.dumps(facts, indent=2), encoding="utf-8")
    print("Live restart checks passed; external retention remains unknown")


if __name__ == "__main__":
    main()
