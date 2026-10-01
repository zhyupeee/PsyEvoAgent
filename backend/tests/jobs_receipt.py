"""Content-free fingerprints of the actual job/budget/grant/result rows across DB restart."""

import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_settings
from app.database import make_engine
from app.models import BackgroundJob, ContextGrant, Idempotency, JobBudget


def main() -> None:
    settings = load_settings()
    if settings.environment != "test" or settings.database_url is None:
        raise RuntimeError("Only an isolated synthetic test database is allowed")
    engine = make_engine(settings.database_url.get_secret_value())
    snapshot: dict[str, object] = {}
    try:
        with Session(engine) as db:
            queries = {
                "background_jobs": select(BackgroundJob.__table__),
                "job_budgets": select(JobBudget.__table__),
                "job_grants": select(ContextGrant.__table__).where(
                    ContextGrant.job_id.is_not(None)
                ),
                "job_results": select(Idempotency.__table__).where(
                    Idempotency.resource_type == "job_probe"
                ),
            }
            for name, query in queries.items():
                rows = list(db.execute(query).mappings())
                assert rows, name
                canonical = sorted(
                    json.dumps(dict(row), sort_keys=True, default=str) for row in rows
                )
                snapshot[name] = {
                    "count": len(rows),
                    "sha256": hashlib.sha256(json.dumps(canonical).encode()).hexdigest(),
                }
            states = set(db.scalars(select(BackgroundJob.status)))
            assert {"succeeded", "failed", "cancelled", "invalidated"} <= states
    finally:
        engine.dispose()
    path = Path(sys.argv[2])
    if sys.argv[1] == "before":
        path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    elif sys.argv[1] == "after":
        assert snapshot == json.loads(path.read_text(encoding="utf-8"))
    else:
        raise ValueError("Expected before or after")
    print(json.dumps({"phase": sys.argv[1], "passed": True, "tables": snapshot}, indent=2))


if __name__ == "__main__":
    main()
