"""Database-backed, purpose-bound, single-use email challenges."""

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import EmailCode, now


def code_digest(key: str, email: str, purpose: str, code: str) -> str:
    return hmac.new(
        key.encode(), f"{purpose}\0{email}\0{code}".encode(), hashlib.sha256
    ).hexdigest()


def reserve_code(db: Session, key: str, email: str, purpose: str) -> tuple[EmailCode, str] | None:
    # Global transaction lock makes quota checks and reservations atomic across API processes.
    db.execute(text("SELECT pg_advisory_xact_lock(330035)"))
    instant = now()
    recent = EmailCode.created_at > instant - timedelta(hours=1)
    total = db.scalar(select(func.count()).select_from(EmailCode).where(recent)) or 0
    count = (
        db.scalar(
            select(func.count()).select_from(EmailCode).where(recent, EmailCode.email == email)
        )
        or 0
    )
    latest = db.scalar(
        select(EmailCode)
        .where(EmailCode.email == email)
        .order_by(EmailCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if (
        total >= 100
        or count >= 5
        or (latest and latest.created_at > instant - timedelta(seconds=60))
    ):
        return None
    rows = db.scalars(
        select(EmailCode)
        .where(
            EmailCode.email == email, EmailCode.purpose == purpose, EmailCode.consumed_at.is_(None)
        )
        .with_for_update()
    )
    for old in rows:
        old.consumed_at = instant
    code = f"{secrets.randbelow(1000000):06d}"
    row = EmailCode(
        email=email,
        purpose=purpose,
        code_hash=code_digest(key, email, purpose, code),
        expires_at=instant + timedelta(minutes=10),
    )
    db.add(row)
    db.flush()
    return row, code


def consume_code(db: Session, key: str, email: str, purpose: str, code: str) -> bool:
    row = db.scalar(
        select(EmailCode)
        .where(EmailCode.email == email, EmailCode.purpose == purpose)
        .order_by(EmailCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if row is None or row.consumed_at or row.expires_at <= now() or row.attempts >= 5:
        return False
    row.attempts += 1
    matched = hmac.compare_digest(row.code_hash, code_digest(key, email, purpose, code))
    if matched or row.attempts >= 5:
        row.consumed_at = now()
    return matched
