"""Additive upgrade, retained facts, typed owner FKs and refusal of lossy downgrade."""

from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, insert
from sqlalchemy.orm import Session

from app.database import make_engine
from app.memory_models import Memory
from app.models import Note, User, now
from tests.test_step03_migrations import migration_url

__all__ = ["migration_url"]
pytestmark = pytest.mark.postgres


def test_memory_upgrade_preserves_records_and_refuses_loss(migration_url: str) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "m013_background_jobs")
    engine = make_engine(migration_url)
    try:
        with Session(engine) as db, db.begin():
            user = User(email="memory-migration@example.com", password_hash="retained")
            db.add(user)
            db.flush()
            note = Note(owner_id=user.id, body="retained source", kind="free", status="saved")
            db.add(note)
            db.flush()
            owner, nid = user.id, note.id
        command.upgrade(config, "head")
        command.check(config)
        command.downgrade(config, "m013_background_jobs")
        command.upgrade(config, "head")
        with Session(engine) as db, db.begin():
            old = db.get(Note, nid)
            assert old and old.body == "retained source"
            db.add(
                Memory(
                    owner_id=owner,
                    content="synthetic migration memory",
                    claim_type="system_inference",
                )
            )
        with pytest.raises(RuntimeError, match="destructive downgrade refused"):
            command.downgrade(config, "m013_background_jobs")
        command.check(config)
    finally:
        engine.dispose()


def test_snapshot_upgrade_only_backfills_the_extracted_source_version(migration_url: str) -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "n014_memory")
    engine = make_engine(migration_url)
    original = {"source_type": "message", "source_id": str(uuid4()), "source_version": 1}
    replacement = {**original, "source_id": str(uuid4())}
    ids = [str(uuid4()), str(uuid4())]
    try:
        old_memories = Table("memories", MetaData(), autoload_with=engine)
        with Session(engine) as db, db.begin():
            user = User(email="snapshot-migration@example.com", password_hash="synthetic-unused")
            db.add(user)
            db.flush()
            for index, ref in enumerate((original, replacement)):
                note = Note(
                    owner_id=user.id,
                    kind="linked_excerpt",
                    status="saved",
                    version=index + 1,
                    source_refs=[ref],
                )
                db.add(note)
                db.flush()
                db.execute(
                    insert(old_memories).values(
                        id=ids[index],
                        owner_id=user.id,
                        content="retained synthetic memory",
                        claim_type="user_statement",
                        status="active",
                        scope="personal_memory",
                        purpose="saved_memory",
                        retention_policy_id="experiment-defaults/1",
                        schema_version=1,
                        version=1,
                        created_at=now(),
                        updated_at=now(),
                        source_refs=[
                            {"source_type": "note", "source_id": note.id, "source_version": 1}
                        ],
                        consent_refs=[],
                    )
                )
        command.upgrade(config, "head")
        command.check(config)
        with Session(engine) as db:
            for mid, expected in zip(ids, ([original], []), strict=True):
                row = db.get(Memory, mid)
                assert row is not None and row.source_snapshot == expected
                assert row.content == "retained synthetic memory" and row.version == 1
        with pytest.raises(RuntimeError, match="destructive downgrade refused"):
            command.downgrade(config, "n014_memory")
    finally:
        engine.dispose()
