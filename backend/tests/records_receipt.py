"""Compare actual synthetic record rows before and after PostgreSQL restart."""

import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import load_settings
from app.database import make_engine
from app.models import ContextGrant, DeletionJob, Note, NoteSource, SleepRecord, SupportCard, User


def main() -> None:
    settings = load_settings()
    if settings.environment != "test" or settings.database_url is None:
        raise RuntimeError("Only an isolated synthetic test database is allowed")
    engine = make_engine(settings.database_url.get_secret_value())
    snapshot: dict[str, object] = {}
    with Session(engine) as db:
        owner = db.scalar(select(User.id).where(User.email == "s2-records-browser@example.com"))
        assert owner is not None
        for model in (Note, SleepRecord, SupportCard, NoteSource, ContextGrant, DeletionJob):
            rows = [
                dict(row)
                for row in db.execute(
                    select(model.__table__).where(model.owner_id == owner)
                ).mappings()
            ]
            canonical = sorted(
                json.dumps(row, sort_keys=True, ensure_ascii=True, default=str) for row in rows
            )
            snapshot[model.__tablename__] = {
                "count": len(rows),
                "sha256": hashlib.sha256(json.dumps(canonical).encode()).hexdigest(),
            }
        assert db.scalar(
            select(Note.id).where(
                Note.owner_id == owner, Note.status == "draft", Note.deleted_at.is_(None)
            )
        )
        assert db.scalar(
            select(SleepRecord.id).where(
                SleepRecord.owner_id == owner,
                SleepRecord.wake_at.is_(None),
                SleepRecord.deleted_at.is_(None),
            )
        )
        card = db.scalar(select(SupportCard).where(SupportCard.owner_id == owner))
        assert card is not None and card.deleted_at and card.previous_content is None
        assert not card.helpful_methods and not card.contact_notes and not card.self_reminders
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
