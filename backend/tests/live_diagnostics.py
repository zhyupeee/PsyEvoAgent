"""Export content-free live call outcomes before the disposable database is removed."""

import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_settings
from app.database import make_engine
from app.models import ModelCall, Run


def main() -> None:
    settings = load_settings()
    assert settings.environment == "test" and settings.database_url is not None
    engine = make_engine(settings.database_url.get_secret_value())
    with Session(engine) as db:
        rows = [
            {
                "run_id": run.id,
                "status": run.status,
                "stop_reason": run.stop_reason,
                "call": call.receipt,
            }
            for run, call in db.execute(
                select(Run, ModelCall).join(ModelCall, ModelCall.run_id == Run.id)
            )
            if call.receipt.get("currency") != "SYNTHETIC"
        ]
    engine.dispose()
    Path(sys.argv[1]).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Exported {len(rows)} live call metadata records; no message content")


if __name__ == "__main__":
    main()
