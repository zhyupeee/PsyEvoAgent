"""Bounded request-local execution with durable idempotency and cancellation."""

import asyncio
from dataclasses import asdict
from datetime import timedelta
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.api import APIError
from app.config import Settings
from app.models import IdentitySession, ProviderTest, Run, User, now
from app.runs import lock_owner
from app.support import CallReceipt


def expire(row: ProviderTest) -> None:
    if row.status == "running" and row.deadline_at <= now():
        row.status, row.reason = "interrupted", "deadline"


def result(row: ProviderTest) -> dict[str, Any]:
    return {
        "passed": row.status == "completed",
        "reason": ("provider_test_running" if row.status == "running" else row.reason),
    }


def reserve(
    db: Session, auth: IdentitySession, key: str, version: int, settings: Settings
) -> ProviderTest:
    # Caller holds the same owner lock as start/logout/config deletion.
    rows = list(
        db.scalars(
            select(ProviderTest).where(
                ProviderTest.owner_id == auth.owner_id, ProviderTest.status == "running"
            )
        )
    )
    for row in rows:
        expire(row)
    if any(row.status == "running" for row in rows):
        raise APIError(409, "provider_test_active")
    recent = db.scalar(
        select(ProviderTest.id)
        .where(
            ProviderTest.owner_id == auth.owner_id,
            ProviderTest.created_at > now() - timedelta(seconds=10),
        )
        .limit(1)
    )
    if recent:
        raise APIError(429, "provider_test_throttled")
    if db.scalar(
        select(Run.id)
        .where(Run.owner_id == auth.owner_id, Run.status.in_({"queued", "running"}))
        .limit(1)
    ):
        raise APIError(409, "run_active")
    row = ProviderTest(
        owner_id=auth.owner_id,
        identity_id=auth.id,
        request_key=key,
        settings_version=version,
        custom=settings.provider_custom_endpoint,
        deadline_at=now() + timedelta(seconds=settings.provider_deadline_seconds),
        # Unknown outcome stays reserved if the process dies before recording actual usage.
        receipt={
            "status": "reserved",
            "reserved_tokens": 8192,
            "actual_tokens": None,
            "role": "configuration_test",
            "currency": "unknown",
        },
    )
    db.add(row)
    db.flush()
    return row


def cancel(
    db: Session, owner: str, *, identity_id: str | None = None, custom: bool = False
) -> None:
    query = select(ProviderTest).where(
        ProviderTest.owner_id == owner, ProviderTest.status == "running"
    )
    if identity_id is not None:
        query = query.where(ProviderTest.identity_id == identity_id)
    if custom:
        query = query.where(ProviderTest.custom.is_(True))
    for row in db.scalars(query):
        row.status = "cancelled"
        row.reason = "identity_revoked" if identity_id else "provider_configuration_revoked"


def allowed(engine: Engine, owner: str, test_id: str) -> bool:
    with Session(engine) as db, db.begin():
        lock_owner(db, owner)
        row = db.get(ProviderTest, test_id)
        if row is None or row.owner_id != owner:
            return False
        expire(row)
        auth, user = db.get(IdentitySession, row.identity_id), db.get(User, owner)
        if (
            not auth
            or auth.owner_id != owner
            or auth.revoked_at
            or auth.expires_at <= now()
            or not user
            or not user.email
            or user.deleted_at
        ):
            if row.status == "running":
                row.status, row.reason = "cancelled", "identity_revoked"
        return row.status == "running"


async def execute(engine: Engine, owner: str, test_id: str, settings: Settings) -> dict[str, Any]:
    from app.provider_probe import probe

    def record(receipt: CallReceipt) -> None:
        with Session(engine) as db, db.begin():
            lock_owner(db, owner)
            row = db.get(ProviderTest, test_id)
            assert row is not None and row.owner_id == owner
            row.receipt = {**asdict(receipt), "role": "configuration_test"}

    task: asyncio.Task[dict[str, object]] | None = None
    revoked = False
    outcome: dict[str, object] = {"status": "failed", "stop_reason": "provider_error"}
    try:
        if allowed(engine, owner, test_id):
            task = asyncio.create_task(
                probe(
                    settings,
                    run_id=test_id,
                    authorize=lambda _: allowed(engine, owner, test_id),
                    record_call=record,
                )
            )
            while not task.done():
                await asyncio.wait({task}, timeout=0.2)
                if not allowed(engine, owner, test_id):
                    revoked = True
                    task.cancel()
                    break
            if not task.cancelled():
                outcome = await task
    except asyncio.CancelledError:
        if not revoked:
            raise
        outcome = {"status": "failed", "stop_reason": "cancelled"}
    except Exception:
        pass  # Never expose provider/credential exception text.
    finally:
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
    with Session(engine) as db, db.begin():
        lock_owner(db, owner)
        row = db.get(ProviderTest, test_id)
        assert row is not None and row.owner_id == owner
        expire(row)
        if row.status == "running":
            row.status = "completed" if outcome["status"] == "passed" else "failed"
            reason = outcome.get("stop_reason")
            row.reason = str(reason) if reason is not None else None
        return result(row)
