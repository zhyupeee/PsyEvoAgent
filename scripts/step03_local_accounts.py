"""One-time STEP03 local maintenance, never called by startup or migrations.

Only the explicitly named local Compose development database is supported.
Credentials are read from the ignored existing local configuration, never printed.
"""

import argparse
import asyncio
import json
import secrets
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx
from sqlalchemy import delete, func, inspect, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from app.database import make_engine
from app.main import create_app
from app.models import Base, User
from tests.mail_support import MemoryMailer, mail_settings


def target_engine():
    # Require this repository's existing Compose service, not an arbitrary localhost listener.
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=psyevoagent",
            "--filter",
            "label=com.docker.compose.service=postgres",
            "--format",
            "{{.ID}}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    ids = result.stdout.split()
    if len(ids) != 1:
        raise RuntimeError(
            "Expected exactly one running local PsyEvoAgent PostgreSQL service"
        )
    details = json.loads(
        subprocess.run(
            ["docker", "inspect", ids[0]],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )[0]
    bindings = details["NetworkSettings"]["Ports"].get("5432/tcp")
    if bindings != [{"HostIp": "127.0.0.1", "HostPort": "55432"}]:
        raise RuntimeError("Unexpected development database port binding")
    config = json.loads((ROOT / ".env.local.json").read_text(encoding="utf-8-sig"))
    url = URL.create(
        "postgresql+psycopg",
        username="psyevo",
        password=config["postgres_password"],
        host="127.0.0.1",
        port=55432,
        database="psyevo_synthetic_dev",
        query={"connect_timeout": "3"},
    )
    engine = make_engine(url.render_as_string(hide_password=False))
    with engine.connect() as connection:
        if connection.execute(
            text("SELECT current_database(), current_user")
        ).one() != ("psyevo_synthetic_dev", "psyevo"):
            raise RuntimeError("Database identity mismatch")
    return engine, url


def cleanup(engine, apply: bool) -> dict:
    expected = set(Base.metadata.tables) | {"alembic_version"}
    order = [
        "context_grants",
        "deletion_jobs",
        "runs",
        "conversations",
        "consent_records",
        "user_preferences",
        "identity_sessions",
        "idempotency_records",
    ]
    with engine.begin() as connection:
        if set(inspect(connection).get_table_names()) != expected:
            raise RuntimeError("Unexpected tables; cleanup refused")
        connection.execute(
            text(
                "LOCK TABLE "
                + ", ".join('"' + name + '"' for name in sorted(expected))
                + " IN EXCLUSIVE MODE"
            )
        )
        # Exact FK graph must match the reviewed metadata, including composite ownership constraints.
        actual = set()
        wanted = set()
        for name, table in Base.metadata.tables.items():
            for fk in inspect(connection).get_foreign_keys(name):
                actual.add(
                    (
                        name,
                        tuple(fk["constrained_columns"]),
                        fk["referred_table"],
                        tuple(fk["referred_columns"]),
                    )
                )
            for fk in table.foreign_key_constraints:
                wanted.add(
                    (
                        name,
                        tuple(col.name for col in fk.columns),
                        fk.referred_table.name,
                        tuple(element.column.name for element in fk.elements),
                    )
                )
        if actual != wanted:
            raise RuntimeError("Unexpected foreign-key graph; cleanup refused")
        targets = select(User.id).where(
            User.email.is_(None), User.username.is_not(None)
        )
        ids = list(connection.scalars(targets))
        counts = {}
        for name in order:
            table = Base.metadata.tables[name]
            counts[name] = connection.scalar(
                select(func.count()).select_from(table).where(table.c.owner_id.in_(ids))
            )
        counts["users"] = len(ids)
        summary = {
            "database": "psyevo_synthetic_dev",
            "host": "127.0.0.1",
            "port": 55432,
            "predicate": "email IS NULL AND username IS NOT NULL",
            "expected_rows": counts,
            "applied": apply,
            "actual_rows": {},
        }
        print(json.dumps(summary, ensure_ascii=True), flush=True)
        if apply:
            for name in order:
                table = Base.metadata.tables[name]
                result = connection.execute(
                    delete(table).where(table.c.owner_id.in_(ids))
                )
                if result.rowcount != counts[name]:
                    raise RuntimeError(
                        "Affected row count changed; transaction rolled back"
                    )
                summary["actual_rows"][name] = result.rowcount
            result = connection.execute(
                delete(User).where(User.id.in_(ids), User.email.is_(None))
            )
            if result.rowcount != counts["users"]:
                raise RuntimeError("Account count changed; transaction rolled back")
            summary["actual_rows"]["users"] = result.rowcount
        return summary


async def seed(engine, url) -> dict:
    email = "admin@psy.com"
    with Session(engine) as db:
        if db.scalar(select(User.id).where(User.email == email)):
            return {
                "email": email,
                "created": False,
                "reason": "already exists; password unchanged",
            }
    path = ROOT / ".env.step03-account.json"
    if path.exists():
        raise RuntimeError("Development credential file already exists; refusing to overwrite")
    password = secrets.token_urlsafe(24)
    mail = MemoryMailer()
    settings = mail_settings(
        environment="development",
        database_url=url.render_as_string(hide_password=False),
        browser_origin="http://127.0.0.1:3000",
    )
    # Validation and registration are the same application code; the capture never reaches a real mailbox.
    app = create_app(settings, mail)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app),
            base_url=settings.browser_origin,
            headers={"Origin": settings.browser_origin},
        ) as client:
            sent = await client.post(
                "/api/v1/auth/registration-codes", json={"email": email}
            )
            if sent.status_code != 202:
                raise RuntimeError("Synthetic registration-code request failed")
            response = await client.post(
                "/api/v1/auth/register",
                json={"email": email, "code": mail.code(email), "password": password},
            )
            if response.status_code != 201:
                raise RuntimeError("Synthetic registration failed")
    path = ROOT / ".env.step03-account.json"
    with path.open("x", encoding="utf-8") as output:
        json.dump(
            {
                "email": email,
                "password": password,
                "database": "psyevo_synthetic_dev",
                "verification": "local synthetic mailbox; no real email verification",
            },
            output,
            indent=2,
        )
        output.write("\n")
    return {
        "email": email,
        "created": True,
        "credential_file": path.name,
        "verification": "synthetic only",
        "administrator_privileges": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-cleanup", action="store_true")
    parser.add_argument("--seed", action="store_true")
    args = parser.parse_args()
    receipt = {"step": "S1-STEP03.5", "at": datetime.now(UTC).isoformat()}
    engine = None
    try:
        engine, url = target_engine()
        receipt["cleanup"] = cleanup(engine, args.apply_cleanup)
        if args.seed:
            if not args.apply_cleanup:
                raise RuntimeError("Seed requires explicit one-time cleanup mode")
            receipt["seed"] = asyncio.run(seed(engine, url))
    except Exception as exc:
        # Never print connection/SMTP exception details or secrets.
        receipt["error_type"] = type(exc).__name__
        if isinstance(exc, RuntimeError):
            receipt["reason"] = str(exc)
            print(str(exc), flush=True)
        print(
            "Local maintenance stopped; no credentials disclosed. See receipt.",
            flush=True,
        )
        raise SystemExit(1) from None
    finally:
        if engine is not None:
            engine.dispose()
        destination = (
            ROOT
            / ".artifacts"
            / (
                "step035-local-"
                + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
                + ".json"
            )
        )
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        print("Receipt: " + str(destination), flush=True)


if __name__ == "__main__":
    main()
