"""Identity, purpose and source authorization for the synthetic STEP03 slice."""

import hmac
import json
import logging
import secrets
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts import (
    ConsentCreate,
    DraftCreate,
    EmailInput,
    GrantCreate,
    Login,
    PasswordChange,
    PasswordReset,
    PreferenceChange,
    Register,
    SessionChange,
    SessionCreate,
    Version,
)
from app.email_identity import consume_code, reserve_code
from app.models import (
    Consent,
    ContextGrant,
    Conversation,
    Idempotency,
    IdentitySession,
    LoginAttempt,
    Personal,
    Preferences,
    Run,
    User,
    now,
)
from app.security import digest, password_hash, password_matches

router = APIRouter(prefix="/api/v1")
COOKIE = "psyevo_session"
# Same password work for unknown emails.
DUMMY_HASH = password_hash("not-an-account-password", "synthetic-dummy-salt")


class APIError(Exception):
    def __init__(self, status: int, code: str) -> None:
        self.status = status
        self.code = code


def database(request: Request) -> Iterator[Session]:
    engine = request.app.state.engine
    if engine is None:
        raise APIError(503, "database_not_configured")
    with Session(engine) as db, db.begin():
        yield db


DB = Annotated[Session, Depends(database, scope="function")]


def check_origin(request: Request) -> None:
    if request.headers.get("origin") != request.app.state.settings.browser_origin:
        raise APIError(403, "origin_rejected")


def identity(request: Request, db: DB) -> IdentitySession:
    auth = db.scalar(
        select(IdentitySession).where(
            IdentitySession.token_hash == digest(request.cookies.get(COOKIE, "")),
            IdentitySession.revoked_at.is_(None),
            IdentitySession.expires_at > now(),
        )
    )
    if auth is None:
        raise APIError(401, "authentication_required")
    # One transaction serializes this owner's writes, grant checks and withdrawal.
    user = db.scalar(select(User).where(User.id == auth.owner_id).with_for_update())
    db.refresh(auth)
    if (
        user is None
        or user.email is None
        or user.deleted_at
        or auth.revoked_at
        or auth.expires_at <= now()
    ):
        raise APIError(401, "authentication_required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), auth.csrf_token):
            raise APIError(403, "csrf_rejected")
    return auth


Auth = Annotated[IdentitySession, Depends(identity, scope="function")]


def owned[T: Personal](db: Session, model: type[T], resource_id: str, owner: str) -> T:
    row = db.scalar(
        select(model).where(
            model.id == resource_id,
            model.owner_id == owner,
            model.deleted_at.is_(None),
        )
    )
    if row is None:
        raise APIError(404, "not_found")
    return row


def bump(row: Personal, version: int) -> None:
    if row.version != version:
        raise APIError(409, "version_conflict")
    row.version += 1
    row.updated_at = now()


def resource(row: Personal) -> dict[str, Any]:
    # Explicit output allowlist: never serialize login hashes, cookies or request bodies.
    result: dict[str, Any] = {
        "id": row.id,
        "schema_version": row.schema_version,
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "deleted_at": None if row.deleted_at is None else row.deleted_at.isoformat(),
        "purpose": row.purpose,
        "retention_policy_id": row.retention_policy_id,
        "source_refs": row.source_refs,
        "consent_refs": row.consent_refs,
    }
    if isinstance(row, Preferences):
        result.update(
            age_band=row.age_band,
            age_source=row.age_source,
            mode=row.mode,
            display_preferences=row.display_preferences,
        )
    elif isinstance(row, Consent):
        result.update(
            decision=row.decision,
            notice_version=row.notice_version,
            scope=row.scope,
            effective_scope=row.scope if consent_valid(row) else [],
            decided_at=row.decided_at.isoformat(),
            expires_at=None,
            revoked_at=None if row.revoked_at is None else row.revoked_at.isoformat(),
        )
    elif isinstance(row, Conversation):
        result.update(session_id=row.id, title=row.title, status=row.status)
    elif isinstance(row, Run):
        result.update(
            run_id=row.id,
            session_id=row.session_id,
            status=row.status,
            expires_at=None,
            stop_reason=row.stop_reason,
            source_message_version=row.source_message_version,
        )
    elif isinstance(row, ContextGrant):
        result.update(
            run_id=row.run_id,
            source_id=row.source_id,
            source_type=row.source_type,
            source_version=row.source_version,
            consent_id=row.consent_id,
            expires_at=None,
            revoked_at=None if row.revoked_at is None else row.revoked_at.isoformat(),
        )
    return result


def consent_valid(row: Consent) -> bool:
    return (
        row.purpose == "service_context"
        and row.decision == "granted"
        and row.revoked_at is None
        and row.deleted_at is None
    )


def grant_valid(db: Session, grant: ContextGrant) -> bool:
    run = db.get(Run, grant.run_id)
    source = db.get(Conversation, grant.source_id)
    if run is None or source is None:
        return False
    session = db.get(Conversation, run.session_id)
    if session is None:
        return False
    return (
        grant.revoked_at is None
        and grant.deleted_at is None
        and run.owner_id == source.owner_id == session.owner_id == grant.owner_id
        and run.deleted_at is None
        and run.status == "draft"
        and session.deleted_at is None
        and session.status == "active"
        and source.deleted_at is None
        and source.status == "active"
        and source.version == grant.source_version
    )


def create_once[T: Personal](
    db: Session,
    request: Request,
    auth: IdentitySession,
    model: type[T],
    body: dict[str, Any],
    build: Callable[[], T],
) -> T:
    key = request.headers.get("idempotency-key", "")
    if not 1 <= len(key) <= 128 or not key.isascii():
        raise APIError(422, "idempotency_key_required")
    fingerprint = digest(request.url.path + json.dumps(body, sort_keys=True, ensure_ascii=True))
    previous = db.get(Idempotency, (auth.owner_id, key))
    if previous is not None:
        if previous.request_hash != fingerprint:
            raise APIError(409, "idempotency_conflict")
        # Reauthorize the current resource; never replay an old sensitive response snapshot.
        return owned(db, model, previous.resource_id, auth.owner_id)
    row: T = build()
    db.add(row)
    db.flush()
    db.add(
        Idempotency(
            owner_id=auth.owner_id,
            key=key,
            request_hash=fingerprint,
            resource_type=model.__name__,
            resource_id=row.id,
        )
    )
    db.flush()
    return row


@router.post("/auth/login")
def login(body: Login, request: Request, response: Response, db: DB) -> dict[str, str]:
    check_origin(request)
    user = db.scalar(select(User).where(User.email == body.email).with_for_update())
    db.execute(
        insert(LoginAttempt)
        .values(email=body.email)
        .on_conflict_do_nothing(index_elements=[LoginAttempt.email])
    )
    attempt = db.get(LoginAttempt, body.email, with_for_update=True)
    assert attempt is not None
    matched = password_matches(body.password, user.password_hash if user else DUMMY_HASH)
    if attempt.locked_until and attempt.locked_until > now():
        raise APIError(429, "login_throttled")
    if user is None or not matched or user.deleted_at is not None:
        attempt.failed_logins += 1
        if attempt.failed_logins >= 5:
            attempt.locked_until = now() + timedelta(minutes=1)
            attempt.failed_logins = 0
        db.commit()  # Keep failed attempts even though the request is rejected.
        raise APIError(401, "invalid_credentials")
    db.delete(attempt)
    user.failed_logins = 0
    user.locked_until = None
    return establish_session(user, request, response, db)


@router.post("/auth/register", status_code=201)
def register(body: Register, request: Request, response: Response, db: DB) -> dict[str, str]:
    check_origin(request)
    verify_email_code(request, db, body.email, "registration", body.code)
    user = User(email=body.email, password_hash=password_hash(body.password))
    try:
        with db.begin_nested():
            db.add(user)
            db.flush()
            db.add(Preferences(owner_id=user.id))
            db.flush()
    except IntegrityError as exc:
        if db.scalar(select(User.id).where(User.email == body.email)) is not None:
            db.commit()
            raise APIError(409, "email_taken") from exc
        raise
    return establish_session(user, request, response, db)


def establish_session(
    user: User, request: Request, response: Response, db: Session
) -> dict[str, str]:
    old = db.scalar(
        select(IdentitySession).where(
            IdentitySession.token_hash == digest(request.cookies.get(COOKIE, ""))
        )
    )
    if old is not None:
        old.revoked_at = now()
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(
        IdentitySession(
            owner_id=user.id,
            token_hash=digest(token),
            csrf_token=csrf,
            expires_at=now() + timedelta(hours=8),
        )
    )
    db.flush()
    response.set_cookie(
        COOKIE,
        token,
        secure=True,
        httponly=True,
        samesite="strict",
        max_age=8 * 3600,
        path="/api/v1",
    )
    assert user.email is not None
    return {"user_id": user.id, "email": user.email, "csrf_token": csrf}


@router.get("/auth/session")
def current_identity(auth: Auth, db: DB) -> dict[str, str]:
    user = db.get(User, auth.owner_id)
    assert user is not None
    assert user.email is not None
    return {"user_id": auth.owner_id, "email": user.email, "csrf_token": auth.csrf_token}


def email_key(request: Request) -> str:
    settings = request.app.state.settings
    if not settings.email_ready:
        raise APIError(503, "email_unavailable")
    return str(settings.email_code_key.get_secret_value())


def send_code(body: EmailInput, request: Request, db: Session, purpose: str) -> dict[str, str]:
    check_origin(request)
    reserved = reserve_code(db, email_key(request), body.email, purpose)
    if reserved is None:
        raise APIError(429, "email_throttled")
    _, code = reserved
    try:
        # Equal delivery behavior for known and unknown addresses avoids enumeration.
        label = "注册" if purpose == "registration" else "重置密码"
        request.app.state.mailer.send(
            body.email,
            f"PsyEvoAgent {label}验证码",
            f"你的{label}验证码：{code}。10分钟内有效，仅可使用一次。若非本人操作，请忽略。",
        )
    except Exception:
        raise APIError(503, "email_unavailable") from None
    return {"message": "如可继续操作，请查看邮箱中的验证码。"}


@router.post("/auth/registration-codes", status_code=202)
def registration_code(body: EmailInput, request: Request, db: DB) -> dict[str, str]:
    return send_code(body, request, db, "registration")


@router.post("/auth/password-reset-codes", status_code=202)
def reset_code(body: EmailInput, request: Request, db: DB) -> dict[str, str]:
    return send_code(body, request, db, "password_reset")


def verify_email_code(request: Request, db: Session, email: str, purpose: str, code: str) -> None:
    if not consume_code(db, email_key(request), email, purpose, code):
        db.commit()  # Failed attempts survive the rejected request.
        raise APIError(400, "invalid_email_code")


def replace_password(db: Session, user: User, password: str) -> None:
    from app.runs import stop_identity_runs

    for identity_id in db.scalars(
        select(IdentitySession.id).where(IdentitySession.owner_id == user.id)
    ):
        stop_identity_runs(db, identity_id)
    user.password_hash = password_hash(password)
    user.failed_logins = 0
    user.locked_until = None
    db.execute(
        update(IdentitySession).where(IdentitySession.owner_id == user.id).values(revoked_at=now())
    )


def password_notice(request: Request, email: str) -> None:
    try:
        request.app.state.mailer.send(
            email,
            "PsyEvoAgent 密码操作通知",
            "邮箱验证码或当前密码校验已完成。如该邮箱关联有效账号，密码已更新且原有会话已退出。若非本人操作，请通过邮箱找回密码。",
        )
    except Exception:
        logging.getLogger("uvicorn.error").warning("identity.password_notice_failed")


@router.post("/auth/password-reset", status_code=204)
def reset_password(body: PasswordReset, request: Request, response: Response, db: DB) -> None:
    check_origin(request)
    verify_email_code(request, db, body.email, "password_reset", body.code)
    user = db.scalar(select(User).where(User.email == body.email).with_for_update())
    if user is not None and user.deleted_at is None:
        replace_password(db, user, body.new_password)
    db.commit()
    response.delete_cookie(COOKIE, path="/api/v1", secure=True, httponly=True, samesite="strict")
    password_notice(request, body.email)


@router.post("/auth/password-change", status_code=204)
def change_password(
    body: PasswordChange, request: Request, response: Response, db: DB, auth: Auth
) -> None:
    user = db.get(User, auth.owner_id)
    assert user is not None and user.email is not None
    if user.locked_until and user.locked_until > now():
        raise APIError(429, "login_throttled")
    if not password_matches(body.current_password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= 5:
            user.failed_logins = 0
            user.locked_until = now() + timedelta(minutes=1)
        db.commit()
        raise APIError(400, "invalid_current_password")
    email = user.email
    replace_password(db, user, body.new_password)
    db.commit()
    response.delete_cookie(COOKIE, path="/api/v1", secure=True, httponly=True, samesite="strict")
    password_notice(request, email)


@router.get("/experiment-config")
def experiment_config(auth: Auth) -> dict[str, Any]:
    return {
        "version": "experiment-defaults/1",
        "defaults": {
            name: True for name in ("support", "memory", "profile", "evaluation", "optimization")
        },
        "implemented": ["account", "preferences", "source_links"],
        "user_consent": False,
    }


@router.post("/auth/logout", status_code=204)
def logout(response: Response, db: DB, auth: Auth) -> None:
    from app.runs import stop_identity_runs

    auth.revoked_at = now()
    stop_identity_runs(db, auth.id)
    response.delete_cookie(COOKIE, path="/api/v1", secure=True, httponly=True, samesite="strict")


@router.get("/me/preferences")
def preferences(db: DB, auth: Auth) -> dict[str, Any]:
    row = db.scalar(select(Preferences).where(Preferences.owner_id == auth.owner_id))
    if row is None:
        raise APIError(503, "preferences_missing")
    return resource(row)


@router.patch("/me/preferences")
def change_preferences(body: PreferenceChange, db: DB, auth: Auth) -> dict[str, Any]:
    row = db.scalar(select(Preferences).where(Preferences.owner_id == auth.owner_id))
    if row is None:
        raise APIError(503, "preferences_missing")
    bump(row, body.expected_version)
    row.age_band = body.age_band
    row.age_source = "not_provided" if body.age_band == "unknown" else "self_reported"
    row.mode = body.mode
    row.display_preferences = body.display_preferences.model_dump()
    db.flush()
    return resource(row)


@router.post("/consents", status_code=201)
def create_consent(body: ConsentCreate, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    if body.purpose != "service_context" and (body.decision == "granted" or body.scope):
        raise APIError(422, "purpose_not_enabled")
    if body.purpose == "service_context" and body.scope != ["current_run"]:
        raise APIError(422, "invalid_scope")

    def build() -> Consent:
        previous = db.scalars(
            select(Consent).where(
                Consent.owner_id == auth.owner_id,
                Consent.purpose == body.purpose,
                Consent.revoked_at.is_(None),
            )
        )
        for item in previous:
            bump(item, item.version)
            item.revoked_at = now()
            item.decision = "revoked"
        return Consent(owner_id=auth.owner_id, **body.model_dump())

    return resource(create_once(db, request, auth, Consent, body.model_dump(), build))


@router.get("/consents")
def consents(db: DB, auth: Auth, cursor: str | None = None) -> dict[str, Any]:
    query = select(Consent).where(Consent.owner_id == auth.owner_id)
    if cursor is not None:
        anchor = db.scalar(query.where(Consent.id == cursor))
        if anchor is None:
            raise APIError(422, "invalid_cursor")
        query = query.where(tuple_(Consent.created_at, Consent.id) < (anchor.created_at, anchor.id))
    rows = db.scalars(query.order_by(Consent.created_at.desc(), Consent.id.desc()).limit(101)).all()
    page = rows[:100]
    return {
        "items": [resource(row) for row in page],
        "next_cursor": page[-1].id if len(rows) > 100 else None,
    }


@router.delete("/consents/{resource_id}")
def revoke_consent(resource_id: str, body: Version, db: DB, auth: Auth) -> dict[str, Any]:
    row = owned(db, Consent, resource_id, auth.owner_id)
    bump(row, body.expected_version)
    row.decision, row.revoked_at = "revoked", now()
    return resource(row)


@router.post("/sessions", status_code=201)
def create_session(body: SessionCreate, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    return resource(
        create_once(
            db,
            request,
            auth,
            Conversation,
            body.model_dump(),
            lambda: Conversation(owner_id=auth.owner_id, title=body.title),
        )
    )


@router.get("/sessions/{resource_id}")
def get_session(resource_id: str, db: DB, auth: Auth) -> dict[str, Any]:
    return resource(owned(db, Conversation, resource_id, auth.owner_id))


@router.patch("/sessions/{resource_id}")
def change_session(resource_id: str, body: SessionChange, db: DB, auth: Auth) -> dict[str, Any]:
    row = owned(db, Conversation, resource_id, auth.owner_id)
    bump(row, body.expected_version)
    row.title = body.title
    return resource(row)


@router.post("/run-drafts", status_code=201)
def create_draft(body: DraftCreate, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    def build() -> Run:
        conversation = owned(db, Conversation, body.session_id, auth.owner_id)
        if conversation.version != body.expected_session_version or conversation.status != "active":
            raise APIError(409, "version_conflict")
        return Run(
            owner_id=auth.owner_id,
            session_id=conversation.id,
            session_version=conversation.version,
        )

    return resource(create_once(db, request, auth, Run, body.model_dump(), build))


@router.get("/runs/{resource_id}")
def get_run(resource_id: str, db: DB, auth: Auth) -> dict[str, Any]:
    from app.runs import snapshot

    row = owned(db, Run, resource_id, auth.owner_id)
    owned(db, Conversation, row.session_id, auth.owner_id)
    return snapshot(db, row)


@router.post("/context-grants", status_code=201)
def create_grant(body: GrantCreate, request: Request, db: DB, auth: Auth) -> dict[str, Any]:
    def build() -> ContextGrant:
        run = owned(db, Run, body.run_id, auth.owner_id)
        source = owned(db, Conversation, body.source_id, auth.owner_id)
        if (
            source.version != body.source_version
            or source.status != "active"
            or run.status != "draft"
        ):
            raise APIError(409, "source_or_run_changed")
        return ContextGrant(
            owner_id=auth.owner_id,
            **body.model_dump(),
            consent_refs=[],
        )

    row = create_once(db, request, auth, ContextGrant, body.model_dump(), build)
    if not grant_valid(db, row):
        raise APIError(403, "grant_inactive")
    return {**resource(row), "active": True}


@router.get("/context-grants/{resource_id}")
def get_grant(resource_id: str, db: DB, auth: Auth) -> dict[str, Any]:
    row = owned(db, ContextGrant, resource_id, auth.owner_id)
    return {**resource(row), "active": grant_valid(db, row)}


@router.delete("/context-grants/{resource_id}")
def revoke_grant(resource_id: str, body: Version, db: DB, auth: Auth) -> dict[str, Any]:
    row = owned(db, ContextGrant, resource_id, auth.owner_id)
    bump(row, body.expected_version)
    row.revoked_at = now()
    return {**resource(row), "active": False}
